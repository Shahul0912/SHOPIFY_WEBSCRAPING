from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from app.scraper import ShopifyScraper
from app.models import BrandInsights, Product
from app.db import SessionLocal
from app.schemas import Brand, BrandInsight
import openai
import os
import re
import json
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

class FetchInsightsRequest(BaseModel):
    website_url: str

class CompetitorInsightsRequest(BaseModel):
    website_url: str

@app.post("/fetch-insights", response_model=BrandInsights)
def fetch_insights(request: FetchInsightsRequest):
    scraper = ShopifyScraper(request.website_url)
    raw_products = scraper.get_product_catalog()
    if not raw_products:
        raise HTTPException(status_code=401, detail="Website not found or no products available.")
    products = []
    for p in raw_products:
        products.append(Product(
            title=p.get('title', ''),
            url=f"{request.website_url.rstrip('/')}/products/{p.get('handle', '')}",
            price=float(p['variants'][0]['price']) if p.get('variants') and p['variants'][0].get('price') else None,
            image=p['images'][0]['src'] if p.get('images') and len(p['images']) > 0 else None
        ))
    raw_hero_products = scraper.get_hero_products()
    hero_products = []
    for hp in raw_hero_products:
        hero_products.append(Product(
            title=hp.get('title', ''),
            url=hp.get('url', ''),
            price=None,
            image=hp.get('image', None)
        ))
    privacy_policy = scraper.get_privacy_policy()
    refund_policy = scraper.get_refund_policy()
    faqs = scraper.get_faqs()
    social_handles = scraper.get_social_handles()
    contact_details = scraper.get_contact_details()
    about = scraper.get_about()
    important_links = scraper.get_important_links()
    insights_obj = BrandInsights(
        product_catalog=products,
        hero_products=hero_products,
        privacy_policy=privacy_policy,
        refund_policy=refund_policy,
        faqs=faqs,
        social_handles=social_handles,
        contact_details=contact_details,
        about=about,
        important_links=important_links
    )
    # Save to DB
    db: Session = SessionLocal()
    try:
        brand = db.query(Brand).filter(Brand.website_url == request.website_url).first()
        if not brand:
            brand = Brand(website_url=request.website_url)
            db.add(brand)
            db.commit()
            db.refresh(brand)
        # Save or update BrandInsight
        insights_json = json.dumps(insights_obj.dict())
        brand_insight = db.query(BrandInsight).filter(BrandInsight.brand_id == brand.id).first()
        if not brand_insight:
            brand_insight = BrandInsight(brand_id=brand.id, insights_json=insights_json)
            db.add(brand_insight)
        else:
            brand_insight.insights_json = insights_json
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        print(f"DB ERROR: {e}")
    finally:
        db.close()
    return insights_obj

@app.post("/fetch-competitors", response_model=List[BrandInsights])
def fetch_competitors(request: CompetitorInsightsRequest):
    try:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = (
            f"List 5 direct competitor Shopify store URLs for the brand at {request.website_url}. "
            "Return only the URLs, one per line."
        )
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0
        )
        content = response.choices[0].message.content
        urls = re.findall(r'https?://[\w\.-]+', content)
        print("Competitor URLs:", urls)
        competitor_insights = []
        for url in urls:
            try:
                scraper = ShopifyScraper(url)
                raw_products = scraper.get_product_catalog()
                products = []
                for p in raw_products:
                    products.append(Product(
                        title=p.get('title', ''),
                        url=f"{url.rstrip('/')}/products/{p.get('handle', '')}",
                        price=float(p['variants'][0]['price']) if p.get('variants') and p['variants'][0].get('price') else None,
                        image=p['images'][0]['src'] if p.get('images') and len(p['images']) > 0 else None
                    ))
                hero_products = [Product(
                    title=hp.get('title', ''),
                    url=hp.get('url', ''),
                    price=None,
                    image=hp.get('image', None)
                ) for hp in scraper.get_hero_products()]
                insights = BrandInsights(
                    product_catalog=products,
                    hero_products=hero_products,
                    privacy_policy=scraper.get_privacy_policy(),
                    refund_policy=scraper.get_refund_policy(),
                    faqs=scraper.get_faqs(),
                    social_handles=scraper.get_social_handles(),
                    contact_details=scraper.get_contact_details(),
                    about=scraper.get_about(),
                    important_links=scraper.get_important_links()
                )
                competitor_insights.append(insights)
            except Exception as e:
                print(f"Error scraping competitor {url}: {e}")
                continue
        if not competitor_insights:
            raise HTTPException(status_code=404, detail="No competitor insights found.")
        return competitor_insights
    except Exception as e:
        print(f"COMPETITOR ENDPOINT ERROR: {e}")
        raise HTTPException(status_code=500, detail=f"Competitor analysis failed: {str(e)}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/brands")
def list_brands(db: Session = Depends(get_db)):
    brands = db.query(Brand).all()
    return [{"id": b.id, "website_url": b.website_url, "created_at": b.created_at} for b in brands]

@app.get("/brands/{brand_id}/insights")
def get_brand_insights(brand_id: int, db: Session = Depends(get_db)):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    insight = db.query(BrandInsight).filter(BrandInsight.brand_id == brand_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="No insights found for this brand")
    import json
    return json.loads(insight.insights_json) 