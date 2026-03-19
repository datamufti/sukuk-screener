#!/bin/sh
chown -R app:app /app/data
exec gosu app uvicorn app.main:app --host 0.0.0.0 --port 8000
