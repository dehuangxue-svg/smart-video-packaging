"""Persistent review state. Export jobs use immutable, explicitly reviewed revisions."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

from core import project_id, read_json

CONTENT_FIELDS = ('video', 'video_clips', 'product_name', 'subtitles', 'speech_segments',
                  'sound_markers', 'visual', 'asr_quality', 'settings', 'model_output')


def revision(project):
    value = {key: project.get(key) for key in CONTENT_FIELDS}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class QueueConflict(ValueError):
    pass


class ReviewQueue:
    def __init__(self, projects):
        self.projects = Path(projects)
        self.path = self.projects / '_review_queue.json'
        self.lock = threading.RLock()
        saved = read_json(self.path) or {'items': []}
        self.batches = saved.get('batches', [])
        self.items = {item['id']: item for item in saved.get('items', [])}
        for item in self.items.values():
            if item.get('processing') in ('queued', 'processing'):
                item.update(processing='error', error='包装任务被中断，可重新包装')
            if item.get('export_status') in ('queued', 'exporting'):
                item.update(export_status='error', export_error='导出任务被中断，可重新导出')
        # Existing saved projects appear in the review list after upgrading.
        for path in self.projects.glob('*.json'):
            if path == self.path:
                continue
            if self.path.exists() and path.stem not in self.items:
                continue
            project = read_json(path) or {}
            if project.get('video'):
                item = self._ensure(project['video'])
                self._sync_project(item, project)
        self._flush()

    def _flush(self):
        atomic_json(self.path, {'version': 1, 'items': list(self.items.values()), 'batches': self.batches})

    def _ensure(self, video):
        video = Path(video).resolve()
        identity = project_id(video)
        if identity not in self.items:
            self.items[identity] = {
                'id': identity, 'video': str(video), 'name': video.name,
                'folder': str(video.parent), 'added_at': time.time(),
                'processing': 'pending', 'revision': '', 'reviewed_revision': '',
                'exported_revision': '', 'export_status': 'idle', 'output': '',
                'error': '', 'export_error': '', 'subtitle_count': 0,
            }
        return self.items[identity]

    def _sync_project(self, item, project):
        current = revision(project)
        item.update(revision=current, subtitle_count=len(project.get('subtitles', [])),
                    quality_status=project.get('asr_quality', {}).get('status', ''),
                    has_analysis=bool(project.get('model_output', {}).get('asr')),
                    ready=bool(project.get('subtitles')) or bool(project.get('model_output', {}).get('asr')))
        if item.get('processing') not in ('queued', 'processing'):
            item['processing'] = 'ready' if item['ready'] else 'pending'

    def _public(self, item):
        value = copy.deepcopy(item)
        value['reviewed'] = bool(value.get('revision')) and value.get('reviewed_revision') == value['revision']
        value['export_current'] = bool(value.get('revision')) and value.get('exported_revision') == value['revision']
        return value

    def listing(self):
        with self.lock:
            return [self._public(item) for item in self.items.values()]

    def add(self, videos):
        with self.lock:
            result = []
            for video in videos:
                item = self._ensure(video)
                project = read_json(self.projects / (item['id'] + '.json'))
                if project:
                    self._sync_project(item, project)
                result.append(item['id'])
            self._flush()
            return result

    def add_batch(self, videos, folder):
        with self.lock:
            identities = self.add(videos)
            batch = {'id': uuid.uuid4().hex, 'name': Path(folder).resolve().name,
                     'folder': str(Path(folder).resolve()), 'added_at': time.time()}
            self.batches.append(batch)
            for identity in identities:
                self.items[identity].setdefault('batches', []).append(batch['id'])
            self._flush()
            return batch['id'], identities

    def batch_listing(self):
        with self.lock:
            return copy.deepcopy(self.batches)

    def save(self, project, *, expected_revision=None, analysis=False):
        with self.lock:
            item = self._ensure(project['video'])
            if not analysis:
                if item['processing'] in ('queued', 'processing'):
                    raise QueueConflict('此视频正在智能包装，请完成后再修改')
                if expected_revision is not None and expected_revision != item['revision']:
                    raise QueueConflict('工程已在其他窗口更新，请重新载入后修改')
            project = copy.deepcopy(project)
            project['revision'] = revision(project)
            atomic_json(self.projects / (item['id'] + '.json'), project)
            if analysis:
                item.update(processing='ready', error='')
            self._sync_project(item, project)
            self._flush()
            return project['revision']

    def approve(self, identity, expected_revision, reviewed=True):
        with self.lock:
            item = self.items[identity]
            if item['processing'] in ('queued', 'processing') or not item.get('ready'):
                raise QueueConflict('请先完成智能包装并检查字幕')
            if not expected_revision or expected_revision != item['revision']:
                raise QueueConflict('工程版本已变化，请保存后重新审阅')
            item['reviewed_revision'] = item['revision'] if reviewed else ''
            self._flush()
            return self._public(item)

    def claim_analysis(self, identities, *, force=False):
        with self.lock:
            rows = [self.items[identity] for identity in dict.fromkeys(identities)]
            rows = [item for item in rows if item['processing'] not in ('queued', 'processing')
                    and item.get('export_status') not in ('queued', 'exporting')
                    and (force or not item.get('ready'))]
            for item in rows:
                item.update(processing='queued', error='')
            self._flush()
            return [copy.deepcopy(item) for item in rows]

    def processing(self, video, status, error=''):
        with self.lock:
            item = self._ensure(video)
            item.update(processing=status, error=error)
            self._flush()

    def claim_exports(self, identities, snapshot_directory=None):
        with self.lock:
            rows = [self.items[identity] for identity in dict.fromkeys(identities)]
            if not rows:
                raise QueueConflict('没有选择要导出的视频')
            snapshots = []
            for item in rows:
                if not self._public(item)['reviewed']:
                    raise QueueConflict('所选视频尚未全部完成审阅：' + item['name'])
                if item['processing'] in ('queued', 'processing') or item['export_status'] in ('queued', 'exporting'):
                    raise QueueConflict('此视频已有进行中的任务：' + item['name'])
                project = read_json(self.projects / (item['id'] + '.json'))
                if not project or revision(project) != item['reviewed_revision']:
                    raise QueueConflict('工程已变化，请重新载入并审阅：' + item['name'])
                # Model traces are not needed for rendering. Keep only the render input
                # in the queue, and read one frozen project at a time in the worker.
                compact = {key: value for key, value in project.items() if key not in ('model_output', 'speech_segments')}
                asr = project.get('model_output', {}).get('asr')
                compact['model_output'] = {'asr': {'quality': asr.get('quality', {})}} if asr else {}
                if snapshot_directory is not None:
                    path = Path(snapshot_directory) / (item['id'] + '.json')
                    atomic_json(path, compact)
                    snapshots.append({'id': item['id'], 'revision': item['revision'], 'snapshot_path': str(path)})
                else:
                    snapshots.append({'id': item['id'], 'revision': item['revision'], 'project': compact})
            for item in rows:
                item.update(export_status='queued', export_error='')
            self._flush()
            return copy.deepcopy(snapshots)

    def export_update(self, identity, status, *, exported_revision='', output='', error=''):
        with self.lock:
            item = self.items[identity]
            item.update(export_status=status, export_error=error)
            if status == 'done':
                item.update(exported_revision=exported_revision, output=output)
            self._flush()

    def remove(self, identities):
        with self.lock:
            rows = [self.items[identity] for identity in identities]
            if any(item['processing'] in ('queued', 'processing') or item['export_status'] in ('queued', 'exporting') for item in rows):
                raise QueueConflict('请等待所选视频的任务结束后再移出列表')
            for identity in identities:
                self.items.pop(identity, None)
            self._flush()
