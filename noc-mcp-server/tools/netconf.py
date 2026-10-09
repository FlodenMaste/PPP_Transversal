from ncclient import manager


def netconf_get(
    host: str,
    username: str,
    password: str,
    port: int = 830,
    filter_xml: str = "<filter type='subtree'></filter>",
) -> dict:

    try:

        with manager.connect(
            host=host,
            port=port,
            username=username,
            password=password,
            hostkey_verify=False,
            allow_agent=False,
            look_for_keys=False,
            timeout=10,
        ) as connection:

            response = connection.get(filter_xml)

            return {
                "status": "success",
                "host": host,
                "port": port,
                "data": response.data_xml,
            }

    except Exception as exc:

        return {
            "status": "error",
            "host": host,
            "port": port,
            "error": str(exc),
        }
