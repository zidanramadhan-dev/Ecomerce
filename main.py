import secrets
import hashlib
import sqlite3  # Built into Python, no pip install required!
from fastapi import FastAPI, HTTPException, status, Depends, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import List, Dict

app = FastAPI(
    title="Simple E-Commerce API",
    description="A basic backend for managing products with permanent SQLite API key storage.",
    version="1.1.0"
)

# --- 1. PERMANENT SQLITE KEY STORAGE SETUP ---
DB_FILE = "database.db"

def init_db():
    """Creates the keys database table automatically on startup if it is missing."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                active INTEGER DEFAULT 1
            )
        """)
        conn.commit()

# Initialize the database file immediately
init_db()


# --- 2. SECURITY & AUTHENTICATION DEPENDENCY ---
API_KEY_NAME = "X-API-Key"
API_KEY_HEADER = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def generate_new_api_key(username: str) -> str:
    """Generates a unique key, hashes it, and saves it permanently to SQLite."""
    raw_key = f"sk_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO api_keys (key_hash, username, active) VALUES (?, ?, ?)",
            (key_hash, username, 1)
        )
        conn.commit()
    return raw_key

async def get_current_user_from_key(api_key: str = Security(API_KEY_HEADER)):
    """Queries SQLite to check if the incoming key hash exists and is active."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key missing from 'X-API-Key' header."
        )
    
    incoming_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, active FROM api_keys WHERE key_hash = ?", (incoming_hash,))
        row = cursor.fetchone()
    
    if not row or row[1] == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or deactivated API key."
        )
        
    return {"user": row[0], "active": bool(row[1])}


# --- 3. IN-MEMORY STORES (Products & Temporary Cart) ---
PRODUCTS = {
    1: {"id": 1, "name": "Wireless Mouse", "price": 29.99, "stock": 10},
    2: {"id": 2, "name": "Mechanical Keyboard", "price": 89.99, "stock": 5},
    3: {"id": 3, "name": "Gaming Monitor", "price": 249.99, "stock": 2},
}
CART: Dict[int, int] = {} 


# --- 4. DATA MODELS ---
class Product(BaseModel):
    id: int
    name: str
    price: float
    stock: int

class CartItem(BaseModel):
    product_id: int
    quantity: int


# --- 5. ROOT & ADMINISTRATIVE ENDPOINTS ---
@app.get("/", tags=["Root"])
def read_root():   
    return {"message": "Welcome to the Simple E-Commerce API! Create a permanent key at /admin/create-key to get started."}

@app.post("/admin/create-key", tags=["Admin Operations"])
def admin_create_key(username: str):
    """Generate a unique API key that saves permanently to the database file."""
    new_key = generate_new_api_key(username)
    return {
        "warning": "Copy this key now! It is securely hashed and cannot be recovered later.",
        "api_key": new_key
    }

@app.post("/admin/revoke-key", tags=["Internal Engine"])
def admin_revoke_key(username: str):
    """Deletes all active database table signatures assigned to this user parameter string."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        
        # Check if user actually has entries before deleting
        cursor.execute("SELECT COUNT(*) FROM api_keys WHERE username = ?", (username,))
        if cursor.fetchone()[0] == 0:
            raise HTTPException(status_code=404, detail=f"No key records found matching client '{username}'.")
            
        # SQL execution step to drop the key matching rows completely
        cursor.execute("DELETE FROM api_keys WHERE username = ?", (username,))
        conn.commit()
        
    return {"detail": f"All credentials linked to user '{username}' have been permanently deleted and blocked."}

# --- 6. SECURED PRODUCT ROUTES ---
@app.get("/products", response_model=List[Product], tags=["Products"], dependencies=[Depends(get_current_user_from_key)])
def get_all_products():
        return list(PRODUCTS.values())

@app.get("/products/{product_id}", response_model=Product, tags=["Products"], dependencies=[Depends(get_current_user_from_key)])
def get_product(product_id: int):
        if product_id not in PRODUCTS:
            raise HTTPException(status_code=404, detail="Product not found")
        return PRODUCTS[product_id]


# --- 7. SECURED SHOPPING CART ROUTES ---
@app.get("/cart", tags=["Cart"])
def view_cart(user: dict = Depends(get_current_user_from_key)):
    """See cart contents. Displays the authenticated username pulled from SQLite."""
    cart_contents = []
    total_price = 0.0
    
    for prod_id, qty in CART.items():
        product = PRODUCTS[prod_id]
        item_total = product["price"] * qty
        total_price += item_total
        cart_contents.append({
            "product_id": prod_id,
            "name": product["name"],
            "quantity": qty,
            "unit_price": product["price"],
            "item_total": round(item_total, 2)
        })
        
    return {
        "authenticated_shopper": user["user"], 
        "cart": cart_contents, 
        "grand_total": round(total_price, 2)
    }

@app.post("/cart", status_code=status.HTTP_201_CREATED, tags=["Cart"], dependencies=[Depends(get_current_user_from_key)])
def add_to_cart(item: CartItem):
        if item.product_id not in PRODUCTS:
            raise HTTPException(status_code=404, detail="Product does not exist")
        
        requested_qty = item.quantity
        available_stock = PRODUCTS[item.product_id]["stock"]
        
        if requested_qty > available_stock:
            raise HTTPException(
                status_code=400, 
                detail=f"Not enough stock. Only {available_stock} items remaining."
            )
            
        CART[item.product_id] = CART.get(item.product_id, 0) + requested_qty
        return {"message": f"Successfully added {requested_qty}x {PRODUCTS[item.product_id]['name']} to cart"}


# --- 8. SECURED CHECKOUT ROUTES ---
@app.post("/checkout", tags=["Checkout"], dependencies=[Depends(get_current_user_from_key)])
def checkout_cart():
        if not CART:
            raise HTTPException(status_code=400, detail="Your shopping cart is empty")
            
        for prod_id, qty in CART.items():
            if PRODUCTS[prod_id]["stock"] < qty:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Stock levels changed. {PRODUCTS[prod_id]['name']} is out of stock."
                )
                
        for prod_id, qty in CART.items():
            PRODUCTS[prod_id]["stock"] -= qty
            
        CART.clear()  
        return {"status": "Success", "message": "Order placed successfully!"}
