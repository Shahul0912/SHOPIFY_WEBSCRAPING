import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
import re
import os
import phonenumbers
import openai
from dotenv import load_dotenv
load_dotenv()

class ShopifyScraper:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')

    def get_product_catalog(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/products.json"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('products', [])
            else:
                return []
        except Exception:
            return []

    def get_hero_products(self) -> List[Dict[str, Any]]:
        html = self.fetch_homepage_html()
        if not html:
            return []
        soup = BeautifulSoup(html, 'html.parser')
        hero_products = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/products/' in href:
                title = a.get_text(strip=True)
                img = a.find('img')
                image_url = img['src'] if img and img.has_attr('src') else None
                product_url = href if href.startswith('http') else f"{self.base_url}{href if href.startswith('/') else '/' + href}"
                hero_products.append({
                    'title': title,
                    'url': product_url,
                    'image': image_url
                })
        seen = set()
        unique_hero_products = []
        for p in hero_products:
            if p['url'] not in seen and p['title']:
                unique_hero_products.append(p)
                seen.add(p['url'])
        return unique_hero_products

    def fetch_homepage_html(self) -> str:
        try:
            resp = requests.get(self.base_url, timeout=10)
            if resp.status_code == 200:
                return resp.text
            else:
                return ""
        except Exception:
            return ""

    def get_policy_text(self, policy_type: str) -> Optional[str]:
        policy_paths = {
            'privacy': ['/policies/privacy-policy', '/pages/privacy-policy', '/privacy-policy'],
            'refund': ['/policies/refund-policy', '/pages/refund-policy', '/refund-policy', '/policies/return-policy', '/pages/return-policy', '/return-policy']
        }
        for path in policy_paths.get(policy_type, []):
            url = f"{self.base_url}{path}"
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    main = soup.find('main') or soup.find('div', {'id': 'MainContent'}) or soup
                    text = main.get_text(separator='\n', strip=True)
                    if text and len(text) > 100:
                        return text
            except Exception:
                continue
        html = self.fetch_homepage_html()
        if not html:
            return None
        soup = BeautifulSoup(html, 'html.parser')
        if policy_type == 'refund':
            keywords = ['refund', 'return', 'exchange']
        else:
            keywords = [policy_type]
        for a in soup.find_all('a', href=True):
            href = a['href'].lower()
            if any(kw in href for kw in keywords):
                url = href if href.startswith('http') else f"{self.base_url}{href if href.startswith('/') else '/' + href}"
                try:
                    resp = requests.get(url, timeout=10)
                    if resp.status_code == 200:
                        soup2 = BeautifulSoup(resp.text, 'html.parser')
                        main = soup2.find('main') or soup2.find('div', {'id': 'MainContent'}) or soup2
                        text = main.get_text(separator='\n', strip=True)
                        if text and len(text) > 100:
                            return text
                except Exception:
                    continue
        if policy_type == 'refund':
            for kw in ['refund', 'return', 'exchange']:
                for section in soup.find_all(['section', 'div', 'p']):
                    if section.get_text() and kw in section.get_text().lower():
                        text = section.get_text(separator='\n', strip=True)
                        if text and len(text) > 50:
                            return text
        return None

    def get_privacy_policy(self) -> Optional[str]:
        return self.get_policy_text('privacy')

    def get_refund_policy(self) -> Optional[str]:
        return self.get_policy_text('refund')

    def extract_faqs_with_llm(self, text: str) -> list:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = (
            "Extract all FAQ question and answer pairs from the following text. "
            "Return as a JSON array of objects with 'question' and 'answer'. "
            "Text:\n" + text
        )
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
                temperature=0
            )
            import json
            content = response.choices[0].message.content
            data = json.loads(content)
            if isinstance(data, list):
                return [faq for faq in data if faq.get('question') and faq.get('answer')]
            return []
        except Exception:
            return []

    def get_faqs(self) -> list:
        faq_paths = [
            '/pages/faq', '/pages/faqs', '/faq', '/faqs',
            '/pages/help', '/help', '/pages/support', '/support',
            '/pages/customer-service', '/customer-service', '/pages/questions', '/questions'
        ]
        checked_urls = set()
        faq_url = None
        for path in faq_paths:
            url = f"{self.base_url}{path}"
            checked_urls.add(url)
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200 and ('faq' in resp.text.lower() or 'question' in resp.text.lower()):
                    faq_url = url
                    break
            except Exception:
                continue
        html = self.fetch_homepage_html()
        candidate_links = []
        if html:
            soup = BeautifulSoup(html, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if not href.startswith('http'):
                    href = f"{self.base_url}{href if href.startswith('/') else '/' + href}"
                if href not in checked_urls:
                    candidate_links.append(href)
        for link in candidate_links:
            try:
                resp = requests.get(link, timeout=10)
                if resp.status_code == 200 and ('faq' in resp.text.lower() or 'question' in resp.text.lower()):
                    faq_url = link
                    break
            except Exception:
                continue
        if not faq_url:
            return []
        try:
            resp = requests.get(faq_url, timeout=10)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, 'html.parser')
            faqs = []
            for item in soup.find_all(class_=['faq', 'faq-item']):
                q = item.find(['h2', 'h3', 'h4', 'strong', 'b'])
                a = item.find('p')
                if q and a:
                    faqs.append({'question': q.get_text(strip=True), 'answer': a.get_text(strip=True)})
            for details in soup.find_all('details'):
                summary = details.find('summary')
                if summary:
                    answer = details.get_text(separator='\n', strip=True).replace(summary.get_text(strip=True), '').strip()
                    faqs.append({'question': summary.get_text(strip=True), 'answer': answer})
            questions = soup.find_all(['h2', 'h3', 'h4', 'b', 'strong'])
            for q in questions:
                next_p = q.find_next_sibling('p')
                if next_p:
                    faqs.append({'question': q.get_text(strip=True), 'answer': next_p.get_text(strip=True)})
                next_list = q.find_next_sibling(['ul', 'ol'])
                if next_list:
                    answer = '\n'.join(li.get_text(strip=True) for li in next_list.find_all('li'))
                    faqs.append({'question': q.get_text(strip=True), 'answer': answer})
            for li in soup.find_all('li'):
                q = li.find(['strong', 'b'])
                if q:
                    answer = li.get_text(strip=True).replace(q.get_text(strip=True), '').strip()
                    if answer:
                        faqs.append({'question': q.get_text(strip=True), 'answer': answer})
            seen = set()
            unique_faqs = []
            for faq in faqs:
                key = (faq['question'], faq['answer'])
                if key not in seen and faq['question'] and faq['answer']:
                    unique_faqs.append(faq)
                    seen.add(key)
            if not unique_faqs:
                all_text = soup.get_text(separator='\n', strip=True)
                unique_faqs = self.extract_faqs_with_llm(all_text)
            return unique_faqs
        except Exception:
            return []

    def get_social_handles(self) -> dict:
        html = self.fetch_homepage_html()
        if not html:
            return {}
        soup = BeautifulSoup(html, 'html.parser')
        social_domains = {
            'instagram': 'instagram.com',
            'facebook': 'facebook.com',
            'tiktok': 'tiktok.com',
            'twitter': 'twitter.com',
            'youtube': 'youtube.com',
            'pinterest': 'pinterest.com',
            'linkedin': 'linkedin.com',
            'snapchat': 'snapchat.com',
            'whatsapp': 'wa.me',
            'telegram': 't.me',
        }
        handles = {}
        for a in soup.find_all('a', href=True):
            href = a['href']
            for platform, domain in social_domains.items():
                if domain in href:
                    handles[platform] = href
        return handles

    def extract_contact_with_llm(self, text: str) -> dict:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = (
            "Extract all email addresses and phone numbers from the following text. "
            "Return them as a JSON object with 'emails' and 'phones' fields. "
            "Text:\n" + text
        )
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0
            )
            import json
            content = response.choices[0].message.content
            data = json.loads(content)
            return {
                "emails": data.get("emails", []),
                "phones": data.get("phones", [])
            }
        except Exception:
            return {"emails": [], "phones": []}

    def get_contact_details(self) -> dict:
        html = self.fetch_homepage_html()
        emails = set()
        phones = set()
        contact_page_url = None
        email_pattern = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
        def is_real_email(email):
            if any(char.isdigit() for char in email.split('@')[1].split('.')[0]):
                return False
            if any(email.endswith(f"@{suffix}") for suffix in ["6.8.6", "1.8.2", "2.0.1", "0.2.6"]):
                return False
            return True
        all_text = ""
        if html:
            soup = BeautifulSoup(html, 'html.parser')
            for tag in soup(['script', 'style', 'noscript', 'svg', 'meta', 'head', 'title', 'link']):
                tag.decompose()
            all_text = soup.get_text(separator='\n', strip=True)
            emails.update([e for e in email_pattern.findall(all_text) if is_real_email(e)])
            for a in soup.find_all('a', href=True):
                href = a['href'].lower()
                if any(x in href for x in ['contact', 'support', 'customer-service']):
                    contact_page_url = href if href.startswith('http') else f"{self.base_url}{href if href.startswith('/') else '/' + href}"
                    break
            for match in phonenumbers.PhoneNumberMatcher(all_text, "IN"):
                num = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
                phones.add(num)
        contact_text = ""
        if contact_page_url:
            try:
                resp = requests.get(contact_page_url, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    for tag in soup(['script', 'style', 'noscript', 'svg', 'meta', 'head', 'title', 'link']):
                        tag.decompose()
                    contact_text = soup.get_text(separator='\n', strip=True)
                    emails.update([e for e in email_pattern.findall(contact_text) if is_real_email(e)])
                    for match in phonenumbers.PhoneNumberMatcher(contact_text, "IN"):
                        num = phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
                        phones.add(num)
            except Exception:
                pass
        emails_list = list(emails)[:5]
        phones_list = list(phones)[:5]
        if not emails_list and not phones_list:
            llm_result = self.extract_contact_with_llm(contact_text or all_text)
            emails_list = llm_result["emails"][:5]
            phones_list = llm_result["phones"][:5]
        return {
            'emails': emails_list,
            'phones': phones_list,
            'contact_page': contact_page_url
        }

    def extract_about_with_llm(self, text: str) -> str:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = (
            "Summarize the following text as a concise brand description suitable for an 'About Us' section. "
            "Return only the summary text.\nText:\n" + text
        )
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return None

    def get_about(self) -> str:
        about_paths = [
            '/pages/about', '/about', '/about-us', '/pages/about-us',
            '/pages/our-story', '/our-story', '/pages/brand-story', '/brand-story'
        ]
        about_url = None
        for path in about_paths:
            url = f"{self.base_url}{path}"
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200 and ('about' in resp.text.lower() or 'story' in resp.text.lower()):
                    about_url = url
                    break
            except Exception:
                continue
        if not about_url:
            html = self.fetch_homepage_html()
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                for a in soup.find_all('a', href=True):
                    href = a['href'].lower()
                    if 'about' in href or 'story' in href:
                        about_url = href if href.startswith('http') else f"{self.base_url}{href if href.startswith('/') else '/' + href}"
                        break
        about_text = None
        if about_url:
            try:
                resp = requests.get(about_url, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    main = soup.find('main') or soup.find('div', {'id': 'MainContent'}) or soup
                    about_text = main.get_text(separator='\n', strip=True)
                    if about_text and len(about_text) > 100:
                        return about_text.strip()
            except Exception:
                pass
        html = self.fetch_homepage_html()
        if html:
            soup = BeautifulSoup(html, 'html.parser')
            all_text = soup.get_text(separator='\n', strip=True)
            summary = self.extract_about_with_llm(all_text)
            if summary:
                return summary
        return None

    def get_important_links(self) -> dict:
        html = self.fetch_homepage_html()
        if not html:
            return {}
        soup = BeautifulSoup(html, 'html.parser')
        keywords = {
            'order_tracking': ['track', 'tracking', 'order status'],
            'contact_us': ['contact'],
            'blog': ['blog'],
            'support': ['support', 'help'],
            'returns': ['return', 'refund', 'exchange'],
            'policy': ['policy'],
            'faq': ['faq', 'questions']
        }
        links = {}
        for a in soup.find_all('a', href=True):
            text = a.get_text(strip=True).lower()
            href = a['href']
            for key, kw_list in keywords.items():
                if any(kw in text or kw in href.lower() for kw in kw_list):
                    url = href if href.startswith('http') else f"{self.base_url}{href if href.startswith('/') else '/' + href}"
                    if key not in links:
                        links[key] = url
        return links 