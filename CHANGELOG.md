# 更新记录

## 0.2.1 — 2026-11-08

### 新增

- 设置卡里的路径选择改用 Windows 原生对话框（COM IFileOpenDialog，Per-Monitor V2 DPI 感知，路径经 Base64 回传，中文不乱码）。

### 变更

- 与 companion-memory、habit-hint 共用同一份 native-picker 实现（独立包各自放一份 `lib/native-picker.js`，改就两边一起改）。
