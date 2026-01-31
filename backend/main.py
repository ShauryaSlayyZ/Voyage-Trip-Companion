from fastapi import FastAPI
from backend.schemas import UserPreferences
from backend.itinerary_generator import generate_itinerary
from fastapi.middleware.cors import CORSMiddleware



app = FastAPI(title="Voyage – Itinerary Generator")
 

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # allow all for hackathon/demo
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.post("/generate-itinerary")
def generate(user: UserPreferences):
    return generate_itinerary(user)
