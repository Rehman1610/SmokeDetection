from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncpg
import asyncio

app = FastAPI()

# Allow frontend or ESP access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# PostgreSQL Neon URL
DATABASE_URL = "postgresql://neondb_owner:npg_JWf7B0ypseAT@ep-dark-hill-a1jhknww-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

# WebSocket clients
websocket_clients = []

# Relay state to be shared across sessions
relay_state = {"fan": 0}  # default OFF

# Data schema from ESP
class SensorData(BaseModel):
    temperature: float
    humidity: float
    mq2: float
    mq5: float
    mq9: float
    mq135: float
    alert: int
    fan: int

# Data schema from React control
class FanControl(BaseModel):
    fan: int  # 0 or 1

@app.on_event("startup")
async def startup():
    app.state.db = await asyncpg.create_pool(DATABASE_URL)

@app.post("/sensor111")
async def receive_sensor_data(data: SensorData):
    # Store data in DB
    await app.state.db.execute("""
        INSERT INTO sensor111 (mq2, mq5, mq9, mq135, temperature, humidity, alert, fan, timestamp)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
    """, data.mq2, data.mq5, data.mq9, data.mq135,
         data.temperature, data.humidity, data.alert, data.fan)

    # Update server-side relay state
    relay_state["fan"] = data.fan

    # Broadcast to all clients
    payload = {
        "temperature": data.temperature,
        "humidity": data.humidity,
        "mq2": data.mq2,
        "mq5": data.mq5,
        "mq9": data.mq9,
        "mq135": data.mq135,
        "alert": data.alert,
        "fan": data.fan
    }

    for ws in websocket_clients:
        try:
            await ws.send_json(payload)
        except:
            websocket_clients.remove(ws)

    return {"status": "received"}

@app.post("/control")
async def control_fan(control: FanControl):
    relay_state["fan"] = control.fan

    # Broadcast new state to clients (including ESP)
    payload = {
        "type": "control",
        "fan": control.fan
    }

    for ws in websocket_clients:
        try:
            await ws.send_json(payload)
        except:
            websocket_clients.remove(ws)

    return {"status": "fan updated", "fan": control.fan}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    websocket_clients.append(websocket)
    try:
        # Send initial relay state
        await websocket.send_json({
            "type": "control",
            "fan": relay_state["fan"]
        })

        while True:
            msg = await websocket.receive_text()
            print("Message from client:", msg)
    except:
        websocket_clients.remove(websocket)

