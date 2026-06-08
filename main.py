from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict

app = FastAPI(
    title="Simple E-Commerce API",
    description="A basic backend for managing products, carts, and checkouts.",
    version="1.0.0"
)

# --- IN-MEMORY DATABASE (Simulating a database for simplicity) ---
PRODUCTS = {
    1: {"id": 1, "name": "Wireless Mouse", "price": 29.99, "stock": 10},
    2: {"id": 2, "name": "Mechanical Keyboard", "price": 89.99, "stock": 5},
    3: {"id": 3, "name": "Gaming Monitor", "price": 249.99, "stock": 2},
}
CART: Dict[int, int] = {}  # Stores product_id -> quantity


# --- DATA MODELS (Pydantic schemas for request validation) ---
class Product(BaseModel):
    id: int
    name: str
    price: float
    stock: int

class CartItem(BaseModel):
    product_id: int
    quantity: int


# --- 1. PRODUCT ROUTES ---
 
@app.get("/", tags=["Root"])
def read_root():   
    """Welcome message for the API root endpoint."""
    return {"message": "Welcome to the Simple E-Commerce API! Explore /products, manage your /cart, and proceed to /checkout."}

@app.get("/products", response_model=List[Product], tags=["Products"])
def get_all_products():
    """Retrieve all available items in the store catalog."""
    return list(PRODUCTS.values())

@app.get("/products/{product_id}", response_model=Product, tags=["Products"])
def get_product(product_id: int):
    """Retrieve details of a specific product by its ID."""
    if product_id not in PRODUCTS:
        raise HTTPException(status_code=404, detail="Product not found")
    return PRODUCTS[product_id]


# --- 2. SHOPPING CART ROUTES ---

@app.get("/cart", tags=["Cart"])
def view_cart():
    """See all items currently inside your shopping cart and calculate total cost."""
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
        
    return {"cart": cart_contents, "grand_total": round(total_price, 2)}

@app.post("/cart", status_code=status.HTTP_201_CREATED, tags=["Cart"])
def add_to_cart(item: CartItem):
    """Add a product to the cart after validating inventory availability."""
    if item.product_id not in PRODUCTS:
        raise HTTPException(status_code=404, detail="Product does not exist")
    
    requested_qty = item.quantity
    available_stock = PRODUCTS[item.product_id]["stock"]
    
    if requested_qty > available_stock:
        raise HTTPException(
            status_code=400, 
            detail=f"Not enough stock. Only {available_stock} items remaining."
        )
        
    # Update cart dictionary
    CART[item.product_id] = CART.get(item.product_id, 0) + requested_qty
    return {"message": f"Successfully added {requested_qty}x {PRODUCTS[item.product_id]['name']} to cart"}


# --- 3. CHECKOUT ROUTES ---

@app.post("/checkout", tags=["Checkout"])
def checkout_cart():
    """Finalize purchase, deduct inventory stock levels, and empty the cart."""
    if not CART:
        raise HTTPException(status_code=400, detail="Your shopping cart is empty")
        
    # Verify stock one more time before finalizing payment/order
    for prod_id, qty in CART.items():
        if PRODUCTS[prod_id]["stock"] < qty:
            raise HTTPException(
                status_code=400, 
                detail=f"Stock levels changed. {PRODUCTS[prod_id]['name']} is out of stock."
            )
            
    # Deduct stock items from database
    for prod_id, qty in CART.items():
        PRODUCTS[prod_id]["stock"] -= qty
        
    CART.clear()  # Empty the cart
    return {"status": "Success", "message": "Order placed successfully! Thank you for your purchase."}
