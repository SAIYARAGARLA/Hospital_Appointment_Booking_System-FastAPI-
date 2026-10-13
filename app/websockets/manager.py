import asyncio
from collections import defaultdict
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.queues:dict[int,set[WebSocket]]=defaultdict(set); self.users:dict[int,set[WebSocket]]=defaultdict(set); self.lock=asyncio.Lock()
    async def connect_queue(self, doctor_id:int, ws:WebSocket):
        await ws.accept(); self.queues[doctor_id].add(ws)
    async def connect_user(self, user_id:int, ws:WebSocket):
        await ws.accept(); self.users[user_id].add(ws)
    async def disconnect(self, ws:WebSocket):
        for group in list(self.queues.values())+list(self.users.values()): group.discard(ws)
    async def queue_broadcast(self, doctor_id:int, data:dict):
        for ws in list(self.queues.get(doctor_id,set())):
            try: await ws.send_json(data)
            except Exception: await self.disconnect(ws)
    async def notify(self, user_id:int, data:dict):
        for ws in list(self.users.get(user_id,set())):
            try: await ws.send_json(data)
            except Exception: await self.disconnect(ws)
manager=ConnectionManager()
