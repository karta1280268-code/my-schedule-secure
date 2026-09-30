# 個人行事曆助理工作區指引 (Personal Schedule Assistant Guidelines)
**指導老師 / 行程主人：黃彥榮**

本工作區專門用於管理黃彥榮老師的個人生活行程與雲端行事曆。

---

## 🛠️ 行程管理操作規範 (CLI Tool Usage)

所有行事曆新增、查詢、刪除操作，**一律透過本目錄下的 `manage_schedule.py` 執行**：

### 1. 查詢行程 (List)
```bash
python3 manage_schedule.py list [YYYY-MM-DD 或 YYYY-MM]
```
- 例：`python3 manage_schedule.py list 2026-10-05`
- 新增任何行程前，**請先查詢該日行程**，確認有無空檔。

### 2. 個人日常瑣事管理（免密碼，隨時自由操作）
- 範疇：剪頭髮、聚餐、買東西、看展、運動、拿藥、私人聚會等生活瑣事。
- **新增**：
  ```bash
  python3 manage_schedule.py add "YYYY-MM-DD" "HH:MM - HH:MM" "行程名稱"
  ```
  - 例：`python3 manage_schedule.py add 2026-10-05 "19:00 - 20:30" "與朋友聚餐"`
- **刪除**：
  ```bash
  python3 manage_schedule.py remove "YYYY-MM-DD" "行程名稱關鍵字"
  ```
  - 例：`python3 manage_schedule.py remove 2026-10-05 "聚餐"`

### 3. 核心公務管理（家教、診所、學校、論文）—— 🔒 需密碼授權
- 範疇：包含「家教、學生A、學生B、芮晨、周秉佑、理化、數學、英文、診所、8J、A14、學校、論文」等項目。
- **安全防護規則**：
  - 若使用者要求修改、新增或刪除上述核心項目，**必須獲得使用者提供的管理員密碼**。
  - 指令需附帶 `--password <密碼>`：
    ```bash
    python3 manage_schedule.py add "YYYY-MM-DD" "HH:MM - HH:MM" "核心公務名稱" --password <密碼>
    python3 manage_schedule.py remove "YYYY-MM-DD" "核心公務名稱" --password <密碼>
    ```
  - 若使用者未提供密碼，請主動向使用者詢問：「修改家教或診所等核心行程需要管理員密碼授權，請輸入密碼以利執行。」

---

## 🛡️ 安全防護機制 (Built-in Guardrails)
1. **時段衝突自動防呆**：若新增時段與任何既有行程（核心行程或已排瑣事）重疊，系統會直接拒絕寫入。
2. **自動推播**：每次執行 `add` 或 `remove` 成功後，腳本會自動將更新加密推送到 GitHub，LINE 提醒與 Email 即刻生效！
