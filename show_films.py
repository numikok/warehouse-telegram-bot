import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pandas as pd
from models import Film
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get the database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create engine and session
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

# Query all films
films = session.query(Film).all()

# Convert to list of dictionaries for easy display
films_data = []
for film in films:
    films_data.append({
        "id": film.id,
        "code": film.code,
        "thickness": film.thickness,
        "panel_consumption": film.panel_consumption,
        "meters_per_roll": film.meters_per_roll,
        "total_remaining": film.total_remaining
    })

# Print as a nice table using pandas
if films_data:
    df = pd.DataFrame(films_data)
    print(df)
else:
    print("No films found in the database.")

# Close the session
session.close() 