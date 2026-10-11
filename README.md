# Production Tracker

A website for the factory intranet: planners create work orders, supervisors record the
work on the floor, managers follow every order, and the Operations Administrator sets up
people, units, products and processes. It works in English and Thai.

เว็บไซต์สำหรับเครือข่ายภายในของโรงงาน ใช้ได้ทั้งภาษาอังกฤษและภาษาไทย

## Where to start / เริ่มต้นที่นี่

| Who / ผู้อ่าน | Read / อ่าน |
|---|---|
| IT: install the server on Windows / ฝ่ายไอที: ติดตั้งเซิร์ฟเวอร์บน Windows | [docs/deployment/windows-intranet.md](docs/deployment/windows-intranet.md) · [ภาษาไทย](docs/deployment/windows-intranet.th.md) |
| Employees, one guide per role / พนักงาน คู่มือแยกตามบทบาท | [docs/user-guides](docs/user-guides/) (English and Thai PDF) |

## Finish-time forecast / พยากรณ์เวลาเสร็จ

The forecast that used to run as a separate ETA server (`server.py`, reading an Excel
file) is now part of the website and reads the website's own database. Managers and
supervisors see an expected finish on every open order card, in the order summary, per
step on the order page, and an "At risk" item under Needs attention when an order is
expected to finish after its due date. The same forecast is available as JSON at
`GET /api/orders/{id}/eta`. The rules and the shift calendar are in
`backend/service/eta_service.py`; no Excel file is needed.

ระบบพยากรณ์เวลาเสร็จ (เดิมคือ `server.py` ที่อ่านไฟล์ Excel) ถูกรวมเข้ากับเว็บไซต์แล้ว และใช้ข้อมูลจากฐานข้อมูลของเว็บไซต์โดยตรง

## What is in this folder / สิ่งที่อยู่ในโฟลเดอร์นี้

| Path | Contents |
|---|---|
| `backend/`, `frontend/`, `main.py` | The website |
| `pyproject.toml`, `uv.lock` | Exact library versions, for installing with uv |
| `requirements.txt` | The same versions, for installing with pip |
| `.python-version` | Python 3.12 |
| `.env.app.example`, `.env.admin.example` | Templates for the two settings files (no passwords) |
| `database/setup.sql` | Creates a new, empty database (run once) |
| `database/first_admin.sql` | Creates the first Operations Administrator (run once) |
| `deploy/windows/` | Windows service definitions, HTTPS (Caddy) configuration and the nightly backup script |
| `docs/` | The installation guide and the user guides |

The two settings files with the database passwords, `.env.app` and `.env.admin`, are not
included on purpose: each server has its own passwords, chosen when its database is created.
They are made on the server from the two `.example` templates (guide, step 6.1). Never
share the finished files.

ไฟล์ตั้งค่า `.env.app` และ `.env.admin` ที่มีรหัสผ่านฐานข้อมูลไม่ได้รวมไว้โดยตั้งใจ ให้สร้างบนเซิร์ฟเวอร์จากไฟล์ตัวอย่าง
`.example` สองไฟล์ (คู่มือ ขั้นตอนที่ 6.1) และห้ามส่งต่อไฟล์ที่กรอกแล้ว
