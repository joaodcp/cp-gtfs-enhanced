import os

import requests
import uuid
from datetime import datetime
from urllib.parse import urlparse
import hashlib
import hmac
import json


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def hmac_sha256(key: bytes | str, data: str) -> bytes:
    if isinstance(key, str):
        key = key.encode()

    return hmac.new(key, data.encode(), hashlib.sha256).digest()


def get_headers(
    method: str,
    url: str,
    payload: dict | None = None,
):
    parsed = urlparse(url)

    host = parsed.netloc
    path = parsed.path
    query = parsed.query

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    date = timestamp[:8]

    user_id = str(uuid.uuid4())

    client = "AndroidElcanoApp"
    content_type = "application/json;charset=utf-8"

    body = json.dumps(payload or {}, separators=(",", ":"))
    body_hash = sha256_hex(body)

    canonical_headers = (
        f"content-type:{content_type}\n"
        f"x-elcano-host:{host}\n"
        f"x-elcano-client:{client}\n"
        f"x-elcano-date:{timestamp}\n"
        f"x-elcano-userid:{user_id}\n"
    )

    signed_headers = (
        "content-type;"
        "x-elcano-host;"
        "x-elcano-client;"
        "x-elcano-date;"
        "x-elcano-userid"
    )

    canonical_request = (
        f"{method}\n"
        f"{path}\n"
        f"{query}\n"
        f"{canonical_headers}"
        f"{signed_headers}\n"
        f"{body_hash}"
    )

    canonical_hash = sha256_hex(canonical_request)

    string_to_sign = (
        f"HMAC-SHA256\n"
        f"{timestamp}\n"
        f"{date}/{client}/{user_id}/elcano_request\n"
        f"{canonical_hash}"
    )

    # derive signing key
    k_date = hmac_sha256(os.getenv("ADIF_SECRET_KEY"), date)
    k_client = hmac_sha256(k_date, client)
    k_signing = hmac_sha256(k_client, "elcano_request")

    signature = hmac.new(
        k_signing,
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()

    authorization = (
        f"HMAC-SHA256 "
        f"Credential={os.getenv('ADIF_ACCESS_KEY')}/{date}/{client}/{user_id}/elcano_request,"
        f"SignedHeaders={signed_headers},"
        f"Signature={signature}"
    )

    return {
        "Content-Type": content_type,
        "X-Elcano-Host": host,
        "X-Elcano-Client": client,
        "X-Elcano-Date": timestamp,
        "X-Elcano-UserId": user_id,
        "Authorization": authorization,
        "User-key": os.getenv("ADIF_USER_KEY"),
    }


def get_adif_arrivals(
    station_code: str,
    traffic_type: str = "ALL",
):
    url = "https://circulacion.api.adif.es/portroyalmanager/secure/circulationpaths/arrivals/traffictype/"

    payload = {
        "commercialService": "BOTH",
        "commercialStopType": "BOTH",
        "page": {
            "pageNumber": 0,
        },
        "stationCode": station_code,
        "trafficType": traffic_type,
    }

    headers = get_headers(
        method="POST",
        url=url,
        payload=payload,
    )

    response = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=15,
    )

    response.raise_for_status()

    return response.json()

def get_adif_circulation(
    commercial_number: str,
):
    url = f"https://circulacion.api.adif.es/portroyalmanager/secure/circulationpathdetails/severalpaths/"

    payload = {
        "allControlPoints": True,
        "commercialNumber": commercial_number
    }

    headers = get_headers(
        method="POST",
        url=url,
        payload=payload,
    )

    response = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=15,
    )

    response.raise_for_status()

    if response.status_code == 204:
        return None

    return response.json()

# if __name__ == "__main__":
    # arrivals_badajoz = get_adif_arrivals("37606")
    # arrivals_vigo = get_adif_arrivals("22308")

    # fp = open("arrivals_adif_badajoz.json", "w")
    # fp2 = open("arrivals_adif_vigo.json", "w")
    # json.dump(arrivals_badajoz, fp, indent=2, ensure_ascii=False)
    # json.dump(arrivals_vigo, fp2, indent=2, ensure_ascii=False)
    # circulation = get_adif_circulation("00485")
    # fp = open("circulation_adif_00485.json", "w")
    # json.dump(circulation, fp, indent=2, ensure_ascii=False)


    # arrivals = get_adif_arrivals("37610")
    # fp = open("arrivals_adif_ghost.json", "w")
    # json.dump(arrivals, fp, indent=2, ensure_ascii=False)

    # arrivals = get_adif_arrivals("37612")
    # fp = open("arrivals_adif_ghost2.json", "w")
    # json.dump(arrivals, fp, indent=2, ensure_ascii=False)