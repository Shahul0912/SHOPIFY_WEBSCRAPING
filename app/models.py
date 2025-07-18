from pydantic import BaseModel
from typing import List, Optional, Dict

class Product(BaseModel):
    title: str
    url: str
    price: Optional[float]
    image: Optional[str]

class BrandInsights(BaseModel):
    product_catalog: List[Product]
    hero_products: List[Product] = []
    privacy_policy: Optional[str] = None
    refund_policy: Optional[str] = None
    faqs: List[Dict] = []
    social_handles: Dict = {}
    contact_details: Dict = {}
    about: Optional[str] = None
    important_links: Dict = {} 