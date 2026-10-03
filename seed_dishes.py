import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Error: SUPABASE_URL or SUPABASE_KEY missing from .env file.")
    exit()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Recipe mapping linking Dishes to Raw Materials from your list
DISH_RECIPES = [
    # 1. Veg Pizza (Selling Price: ₹250)
    {"dish_name": "Veg Pizza", "selling_price": 250.00, "ingredient_name": "Flour (white)", "quantity_required": 0.2, "unit": "kg"},
    {"dish_name": "Veg Pizza", "selling_price": 250.00, "ingredient_name": "Yeast", "quantity_required": 0.05, "unit": "packet"},
    {"dish_name": "Veg Pizza", "selling_price": 250.00, "ingredient_name": "Cheese", "quantity_required": 0.1, "unit": "kg"},
    {"dish_name": "Veg Pizza", "selling_price": 250.00, "ingredient_name": "Tomato", "quantity_required": 0.15, "unit": "kg"},
    {"dish_name": "Veg Pizza", "selling_price": 250.00, "ingredient_name": "Paneer", "quantity_required": 0.1, "unit": "kg"},

    # 2. Non Veg Pizza (Selling Price: ₹350)
    {"dish_name": "Non Veg Pizza", "selling_price": 350.00, "ingredient_name": "Flour (white)", "quantity_required": 0.2, "unit": "kg"},
    {"dish_name": "Non Veg Pizza", "selling_price": 350.00, "ingredient_name": "Yeast", "quantity_required": 0.05, "unit": "packet"},
    {"dish_name": "Non Veg Pizza", "selling_price": 350.00, "ingredient_name": "Cheese", "quantity_required": 0.1, "unit": "kg"},
    {"dish_name": "Non Veg Pizza", "selling_price": 350.00, "ingredient_name": "Chicken", "quantity_required": 0.15, "unit": "kg"},
    {"dish_name": "Non Veg Pizza", "selling_price": 350.00, "ingredient_name": "Spices", "quantity_required": 0.02, "unit": "kg"},

    # 3. Salad (Selling Price: ₹180)
    {"dish_name": "Salad", "selling_price": 180.00, "ingredient_name": "Lettuce", "quantity_required": 0.2, "unit": "kg"},
    {"dish_name": "Salad", "selling_price": 180.00, "ingredient_name": "Tomato", "quantity_required": 0.1, "unit": "kg"},
    {"dish_name": "Salad", "selling_price": 180.00, "ingredient_name": "Salt", "quantity_required": 0.01, "unit": "kg"},
    {"dish_name": "Salad", "selling_price": 180.00, "ingredient_name": "Spices", "quantity_required": 0.01, "unit": "kg"}
]

def seed_dish_recipes():
    print("🌱 Seeding dish recipes into Supabase...")
    
    # Replace only the dishes seeded here, so dishes you added in the app are left alone
    seeded = sorted({r["dish_name"] for r in DISH_RECIPES})
    supabase.table("dish_recipes").delete().in_("dish_name", seeded).execute()

    # Insert recipes
    supabase.table("dish_recipes").insert(DISH_RECIPES).execute()
    print("✅ Successfully seeded Veg Pizza, Non Veg Pizza, and Salad recipes!")

if __name__ == "__main__":
    seed_dish_recipes()