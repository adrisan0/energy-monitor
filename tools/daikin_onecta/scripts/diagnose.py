from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from daikin_onecta import DaikinClient
from daikin_onecta.errors import DaikinError
from daikin_onecta.local import LegacyLocalDaikin


async def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    hosts = [x.strip() for x in os.getenv("DAIKIN_LOCAL_HOSTS", "").split(",") if x.strip()]
    for host in hosts:
        adapter = LegacyLocalDaikin(host)
        try:
            info = await adapter.get_basic_info()
            control = await adapter.get_control_info()
            print(f"Local {host}: basic_info keys={sorted(info)} control_info keys={sorted(control)}")
        except DaikinError as exc:
            print(f"Local {host}: {exc}")
        finally:
            await adapter.close()
    if os.getenv("DAIKIN_TOKEN_URL") and os.getenv("DAIKIN_API_BASE_URL"):
        client = DaikinClient(
            api_base_url=os.environ["DAIKIN_API_BASE_URL"], token_url=os.environ["DAIKIN_TOKEN_URL"],
            client_id=os.getenv("DAIKIN_CLIENT_ID", ""), client_secret=os.getenv("DAIKIN_CLIENT_SECRET"),
            redirect_uri=os.getenv("DAIKIN_REDIRECT_URI"), scopes=os.getenv("DAIKIN_SCOPES"),
            authorization_code=os.getenv("DAIKIN_AUTHORIZATION_CODE"), refresh_token=os.getenv("DAIKIN_REFRESH_TOKEN"),
            devices_path=os.getenv("DAIKIN_DEVICES_PATH"), status_path_template=os.getenv("DAIKIN_STATUS_PATH_TEMPLATE"),
        )
        try:
            devices = await client.list_devices()
            print(f"ONECTA: autenticación y enumeración correctas; {len(devices)} dispositivo(s).")
            for device in devices:
                print(f"- id={device.id} name={device.name or '(sin nombre)'}")
        except DaikinError as exc:
            print(f"ONECTA: {exc}")
        finally:
            await client.close()
    else:
        print("ONECTA: pendiente; configura las credenciales y rutas oficiales del portal en .env.")


if __name__ == "__main__":
    asyncio.run(main())
