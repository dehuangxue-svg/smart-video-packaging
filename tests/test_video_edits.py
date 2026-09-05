import unittest
from editing import normalize_clips, edit_duration, edit_key
from app import VideoRequest, ProjectRequest
from core import validate_project


class VideoEditTests(unittest.TestCase):
    def test_legacy_project_keeps_full_source_and_empty_is_distinct(self):
        self.assertEqual(edit_duration(normalize_clips(None, 10)), 10)
        self.assertEqual(normalize_clips([], 10), [])
        self.assertIsNone(ProjectRequest(video='x').video_clips)

    def test_invalid_ranges_are_rejected(self):
        for start,end in [(-1,3),(4,2),(2,11),(10.01,10.02),(float('nan'),2)]:
            with self.assertRaises(ValueError):
                normalize_clips([{'source_start':start,'source_end':end}],10)

    def test_cuts_survive_request_and_change_cache_identity(self):
        clips=[{'source_start':1,'source_end':3},{'source_start':6,'source_end':8}]
        self.assertEqual(ProjectRequest(video='x',video_clips=clips).model_dump()['video_clips'],clips)
        self.assertEqual(VideoRequest(video='x',video_clips=clips).video_clips,clips)
        self.assertNotEqual(edit_key(normalize_clips(None,10)),edit_key(normalize_clips(clips,10)))

    def test_basic_edit_without_packaging_can_export_but_timing_errors_cannot(self):
        project={'video_clips':[{'source_start':1,'source_end':3}], 'subtitles':[]}
        self.assertFalse(any(x['level']=='error' for x in validate_project(project,{'duration':2})))
        project['subtitles']=[{'start':1,'end':5,'text':'outside'}]
        self.assertTrue(any(x['level']=='error' for x in validate_project(project,{'duration':2})))


if __name__=='__main__': unittest.main()
