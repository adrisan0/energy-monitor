Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script = @'
import asyncio
from app.db.session import get_session_factory, init_engine
from app.workers.poller import poll_once

async def main():
    init_engine()
    with get_session_factory()() as db:
        for _ in range(5):
            await poll_once(db)

asyncio.run(main())
'@

$script | docker compose exec -T worker python -
