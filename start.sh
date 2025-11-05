#!/usr/bin/env bash
# รัน Gunicorn โดยชี้ไปที่ app object ในไฟล์ app.py
# รูปแบบ: gunicorn [ชื่อไฟล์]:[ชื่อตัวแปร Flask app]
gunicorn app:app