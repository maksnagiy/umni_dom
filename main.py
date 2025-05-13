import requests
import json
import time
import csv
from datetime import datetime
import asyncio
import aiohttp

# токен
OAUTH_TOKEN = "abc123" #писать токен от своего умного дома чето-нехочу

# CSV лог-файл
LOG_FILE = "yandex_device_log.csv"

HEADERS = {
    "Authorization": f"Bearer {OAUTH_TOKEN}"
}

def get_devices():
    url = "https://api.iot.yandex.net/v1.0/user/info"
    response = requests.get(url, headers=HEADERS)
    if response.ok:
        return response.json().get("devices", [])
    else:
        print("Ошибка при получении списка устройств:", response.text)
        return []

async def get_device_state(session, device_id):
    url = f"https://api.iot.yandex.net/v1.0/devices/{device_id}"
    async with session.get(url, headers=HEADERS) as response:
        if response.status == 200:
            data = await response.json()
            capabilities = data.get("capabilities", [])
            for cap in capabilities:
                if cap.get("type") == "devices.capabilities.on_off":
                    if cap.get("state") and "value" in cap["state"]:
                        value = cap["state"]["value"]
                        last_updated = cap.get("last_updated")
                        return device_id, value, last_updated
        return device_id, None, None

def get_room_map():
    url = "https://api.iot.yandex.net/v1.0/user/info"
    response = requests.get(url, headers=HEADERS)
    if response.ok:
        data = response.json()
        # Создаём словарь: room_id -> room_name
        rooms = {room["id"]: room["name"] for room in data.get("rooms", [])}
        return rooms
    else:
        print("Ошибка при получении комнат:", response.text)
        return {}


def log_state(device_id, device_name, state, room_name, last_updated=None):
    if last_updated:
        now = datetime.fromtimestamp(last_updated).isoformat()
    else:
        now = datetime.now().isoformat()

    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([now, room_name, device_id, device_name, state])
    print(f"[{now}] ({room_name}) {device_name} -> {'ON' if state else 'OFF'}")

def get_devices_with_household(household_id_filter=None):
    url = "https://api.iot.yandex.net/v1.0/user/info"
    response = requests.get(url, headers=HEADERS)
    if not response.ok:
        print("Ошибка при получении user_info:", response.text)
        return []

    data = response.json()

    # создаём карту room_id → household_id
    room_to_house = {}
    for room in data.get("rooms", []):
        room_id = room["id"]
        house_id = room.get("household_id")
        if room_id and house_id:
            room_to_house[room_id] = house_id

    filtered_devices = []
    for device in data.get("devices", []):
        room_id = device.get("room")
        house_id = room_to_house.get(room_id)
        if household_id_filter and house_id != household_id_filter:
            continue  # фильтруем по дому
        device["household_id"] = house_id  # добавим в структуру, если нужно дальше
        filtered_devices.append(device)

    return filtered_devices

async def monitor(interval=5, household_id_filter=None):
    devices = get_devices_with_household(household_id_filter)
    room_map = get_room_map()

    print("Типы всех устройств:")
    for d in devices:
        print(f"- {d['name']} → {d.get('type')}")
    light_devices = [d for d in devices if d.get("type") in ["devices.types.light", "devices.types.light.ceiling"]]
    print(f"Найдено устройств после фильтрации по дому: {len(devices)}")
    print(f"Найдено светильников: {len(light_devices)}")
    for dev in light_devices:
        print(f"- {dev['name']}")

    last_states = {}

    async with aiohttp.ClientSession() as session:
        while True:
            tasks = [get_device_state(session, device["id"]) for device in light_devices]
            results = await asyncio.gather(*tasks)

            for device in light_devices:
                device_id = device["id"]
                name = device["name"]
                room_id = device.get("room")
                room_name = room_map.get(room_id, "Без комнаты")

                # Ищем результат
                for res_device_id, current_state, last_updated in results:
                    if res_device_id == device_id:
                        break

                if current_state is None:
                    continue

                if device_id not in last_states:
                    last_states[device_id] = current_state
                    log_state(device_id, name, current_state, room_name, last_updated)
                elif last_states[device_id] != current_state:
                    last_states[device_id] = current_state
                    log_state(device_id, name, current_state, room_name, last_updated)

            await asyncio.sleep(interval)


if __name__ == "__main__":
    try:
        with open(LOG_FILE, "x") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "room", "device_id", "device_name", "state"])
    except FileExistsError:
        pass

    YOUR_HOUSEHOLD_ID = "bf14cf28-157a-48bf-b854-9ddf20d9c4eb"

    asyncio.run(monitor(interval=5, household_id_filter=YOUR_HOUSEHOLD_ID))

