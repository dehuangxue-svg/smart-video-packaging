# Local service / 本地服务

This application is designed for one trusted user's Windows computer. The API listens on `127.0.0.1:8765`, reads paths on that computer, and has no multi-user authentication or remote hosting support. Keep it bound to loopback; it is not a public web service.

本程序面向本机可信用户，接口读取本机路径，不具备多用户认证或公网部署能力。请保持监听 `127.0.0.1`。

When reporting a bug, share a minimal reproduction that you may publish. Do not include credentials, private video, complete local logs, or training snapshots in a public issue. 本机路径、原视频和训练快照可能包含私人内容，公开反馈请使用可公开的最小样例。
