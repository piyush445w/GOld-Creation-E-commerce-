import hashlib
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flask import url_for
from app import create_app, db
from app.models.category import Category
from app.models.currency import Currency
from app.models.product import Product
from app.models.product_media import ProductMedia
from app.models.product_variant import ProductVariant
from app.models.site_setting import SiteSetting
from app.models.user import User
from werkzeug.security import generate_password_hash

app = create_app(os.environ.get('FLASK_ENV', 'development'))

PICS_DIR = os.environ.get('PICS_DIR') or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pics')
if not os.path.isdir(PICS_DIR):
    print(f'PICS_DIR not found: {PICS_DIR}')

MIME_TYPES = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'webp': 'image/webp',
    'avif': 'image/avif',
    'mp4': 'video/mp4',
    'webm': 'video/webm',
}

IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'avif'}

PRODUCT_MEDIA_FILES = {
    'Kundan Necklace Set': ['jwellery/ee7da34b-6cce-4e35-999b-ef74d63855ce.jpg'],
    'Oxidized Silver Jhumkas': ['jwellery/7ac7557e-5d51-47c2-854a-a1017ca2aa27.jpg'],
    'Temple Gold Plated Necklace': ['jwellery/d753e85b-65a6-4b6d-8798-a9455423cc74.jpg'],
    'Meenakari Bangles Set': ['jwellery/EaWMKzCfJPDERCZbwicxpGYPkn52HojdbnRl94bu.jpg'],
    'Pearl Maang Tikka': ['jwellery/jaLDfytZ9TmIRVo1LEsx15ESzYam9EBTtH6uOsOa.jpg'],
    'Choker with Earrings Set': ['jwellery/thumb-copygn-d000920071.jpg'],
    'Banarasi Silk Saree with Zari Work': [
        'sarees/1/peach-satin-saree-with-cut-dana-and-sequin-floral-jaal-embroidery-sg411836-1.avif',
        'sarees/1/SG411836.webm',
    ],
    'Kanchipuram Silk Saree': [
        'sarees/3/pista-green-tissue-organza-woven-saree-with-heavy-hand-embroidery-sg346411-1.avif',
        'sarees/2/SG413534.webm',
    ],
    'Chiffon Printed Saree': ['sarees/2/simply-otp-login-modal-mobile.avif'],
    'Anarkali Cotton Kurta': [
        'kurti/1/asymmetric-purple-kurti-coord-with-mirror-work-and-leheriya-border-sg383462-1_9107055c-2653-4b4d-a7de-eb6fd6aa3312.avif',
        'kurti/1/SG383462.webm',
    ],
}

# Video media uses the first image of the same product as its poster/thumbnail.
VIDEO_THUMBNAIL_SOURCE = {
    'Banarasi Silk Saree with Zari Work': 0,
    'Kanchipuram Silk Saree': 0,
    'Anarkali Cotton Kurta': 0,
}


def truncate_tables(session):
    session.execute('SET FOREIGN_KEY_CHECKS = 0')
    for table in reversed(session.metadata.sorted_tables):
        session.execute(table.delete())
    session.execute('SET FOREIGN_KEY_CHECKS = 1')
    session.commit()


def _media_info_for(rel_path):
    ext = rel_path.rsplit('.', 1)[-1].lower()
    mime_type = MIME_TYPES.get(ext, 'application/octet-stream')
    media_type = 'image' if ext in IMAGE_EXTENSIONS else 'video'
    return ext, mime_type, media_type


def _read_media_file(rel_path):
    absolute = os.path.join(PICS_DIR, rel_path.replace('/', os.sep))
    if not os.path.isfile(absolute):
        print(f'  ! missing media file, skipped: {rel_path}')
        return None
    with open(absolute, 'rb') as handle:
        data = handle.read()
    return {
        'data': data,
        'size': len(data),
        'checksum': hashlib.sha256(data).hexdigest(),
        'filename': os.path.basename(rel_path),
    }


def seed_product_media(product, product_name):
    rel_paths = PRODUCT_MEDIA_FILES.get(product_name)
    created = []

    if rel_paths:
        stored_files = []
        for rel_path in rel_paths:
            stored = _read_media_file(rel_path)
            if stored is None:
                continue
            ext, mime_type, media_type = _media_info_for(rel_path)
            stored.update({'mime_type': mime_type, 'media_type': media_type})
            stored_files.append(stored)

        if stored_files:
            records = []
            for order, stored in enumerate(stored_files):
                media = ProductMedia(
                    product_id=product.id,
                    media_type=stored['media_type'],
                    media_url='',
                    mime_type=stored['mime_type'],
                    display_order=order,
                    is_primary=order == 0,
                    is_active=True,
                    media_data=stored['data'],
                    file_size=stored['size'],
                    original_filename=stored['filename'],
                    checksum=stored['checksum'],
                )
                db.session.add(media)
                records.append((media, stored))
            db.session.flush()

            thumbnail_index = VIDEO_THUMBNAIL_SOURCE.get(product_name)
            with app.test_request_context():
                for media, stored in records:
                    media_url = url_for(
                        'media.serve_product_media',
                        product_id=product.id,
                        media_id=media.id,
                        _external=False,
                    )
                    media.media_url = media_url
                    if media.media_type == 'image':
                        media.thumbnail_url = media_url
                    elif thumbnail_index is not None:
                        thumb_media = records[thumbnail_index][0]
                        media.thumbnail_url = thumb_media.media_url
                    created.append(media)
            return created

    media_url = 'https://via.placeholder.com/600x600?text=' + product_name.replace(' ', '+')
    media = ProductMedia(
        product_id=product.id,
        media_type='image',
        media_url=media_url,
        thumbnail_url=media_url,
        display_order=0,
        is_primary=True,
        is_active=True,
    )
    db.session.add(media)
    created.append(media)
    return created


FORCE = '--force' in sys.argv


with app.app_context():
    db.create_all()
    
    if FORCE:
        truncate_tables(db.session)
    
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@goldcreation.com')
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
    if not User.query.filter_by(role='admin').first():
        admin = User(
            name='Admin',
            email=admin_email,
            password_hash=generate_password_hash(admin_password),
            role='admin'
        )
        db.session.add(admin)
        print(f'Default admin created: {admin_email} / {admin_password}')
    
    currencies = [
        ('INR', 'INR', 1.0, True),
        ('USD', '$', 83.0, True),
    ]
    for code, symbol, rate, settlement in currencies:
        if not Currency.query.filter_by(code=code).first():
            c = Currency(code=code, symbol=symbol, exchange_rate_to_inr=rate, is_settlement_enabled=settlement)
            db.session.add(c)
    
    settings = [
        ('hero_heading', 'Woven in Pure Gold and Heritage Silks'),
        ('hero_subtext', 'Hand-loomed Banarasi brocades, royal velvet lehengas, and heirloom-tissue weaves crafted by generational master weavers in the historic ghats of Varanasi and the royal courts of Chanderi.'),
        ('footer_text', 'Preserving centuries of imperial handloom traditions across Varanasi, Kanchipuram, and Awadh. Gold Creation crafts heirloom weaves, bridal couture suites, and bespoke home linens for the modern global tastemaker.'),
        ('announcement_bar', ''),
        ('primary_accent_color', '#8B1E3F'),
        ('secondary_accent_color', '#C9A227'),
        ('contact_email', 'info@goldcreation.com'),
        ('contact_phone', '+919876543210'),
        ('social_links', ''),
    ]
    for key, value in settings:
        if not SiteSetting.query.filter_by(setting_key=key).first():
            s = SiteSetting(setting_key=key, setting_value=value)
            db.session.add(s)
    
    category_data = [
        ('Jewelry', 'jewelry', 'Traditional and contemporary Indian jewelry'),
        ('Sarees', 'sarees', 'Handloom and designer sarees'),
        ('Kurtis', 'kurtis', 'Ethnic wear kurtis and kurta sets'),
        ('Accessories', 'accessories', 'Bags, footwear, and ethnic accessories'),
    ]
    categories = {}
    for name, slug, description in category_data:
        if not Category.query.filter_by(slug=slug).first():
            cat = Category(name=name, slug=slug, description=description)
            db.session.add(cat)
            categories[name] = cat
        else:
            categories[name] = Category.query.filter_by(slug=slug).first()
    db.session.commit()
    
    def make_slug(name):
        return name.lower().replace(' ', '-')
    
    products = [
        {
            'name': 'Kundan Necklace Set',
            'category': 'Jewelry',
            'description': 'Royal Kundan necklace set with uncut diamonds and enamel detailing. A timeless piece for weddings and festive occasions.',
            'base_price': 8500,
            'variants': [
                {'size': 'Medium', 'price_override': None, 'stock': 10},
                {'size': 'Large', 'price_override': 9500, 'stock': 8},
            ],
        },
        {
            'name': 'Oxidized Silver Jhumkas',
            'category': 'Jewelry',
            'description': 'Intricately crafted oxidized silver jhumkas with antique finish. Lightweight and elegant for daily ethnic wear.',
            'base_price': 1200,
            'variants': [
                {'color': 'Antique Silver', 'price_override': None, 'stock': 25},
                {'color': 'Polished Silver', 'price_override': 1300, 'stock': 20},
            ],
        },
        {
            'name': 'Temple Gold Plated Necklace',
            'category': 'Jewelry',
            'description': 'South Indian temple-inspired gold-plated necklace featuring traditional motifs and intricate carving.',
            'base_price': 5500,
            'variants': [
                {'size': '16 inch', 'price_override': None, 'stock': 12},
                {'size': '18 inch', 'price_override': 6000, 'stock': 10},
                {'size': '20 inch', 'price_override': 6500, 'stock': 8},
            ],
        },
        {
            'name': 'Meenakari Bangles Set',
            'category': 'Jewelry',
            'description': 'Set of 6 traditional Meenakari bangles with colorful enamel work and gold plating. Perfect for bridal and festive looks.',
            'base_price': 2800,
            'variants': [
                {'color': 'Red-Green', 'price_override': None, 'stock': 15},
                {'color': 'Blue-Gold', 'price_override': 3000, 'stock': 12},
            ],
        },
        {
            'name': 'Pearl Maang Tikka',
            'category': 'Jewelry',
            'description': 'Elegant pearl maang tikka with gold-plated chain and central stone pendant. Enhances bridal and festive attire.',
            'base_price': 3200,
            'variants': [
                {'color': 'White Pearl', 'price_override': None, 'stock': 18},
                {'color': 'Black Pearl', 'price_override': 3500, 'stock': 14},
            ],
        },
        {
            'name': 'Banarasi Silk Saree with Zari Work',
            'category': 'Sarees',
            'description': 'Pure Banarasi silk saree with intricate zari work and traditional floral motifs. Includes matching blouse piece.',
            'base_price': 12000,
            'variants': [
                {'color': 'Royal Red', 'price_override': None, 'stock': 5},
                {'color': 'Deep Maroon', 'price_override': 12500, 'stock': 5},
                {'color': 'Navy Blue', 'price_override': 13000, 'stock': 4},
            ],
        },
        {
            'name': 'Kanchipuram Silk Saree',
            'category': 'Sarees',
            'description': 'Authentic Kanchipuram silk saree woven with pure gold zari and temple border. A heirloom piece for special occasions.',
            'base_price': 15000,
            'variants': [
                {'color': 'Traditional Gold', 'price_override': None, 'stock': 3},
                {'color': 'Emerald Green', 'price_override': 16000, 'stock': 3},
            ],
        },
        {
            'name': 'Chiffon Printed Saree',
            'category': 'Sarees',
            'description': 'Lightweight chiffon saree with contemporary digital prints and satin border. Ideal for casual and office wear.',
            'base_price': 2500,
            'variants': [
                {'color': 'Multi-color Floral', 'price_override': None, 'stock': 20},
                {'color': 'Pastel Abstract', 'price_override': 2700, 'stock': 18},
            ],
        },
        {
            'name': 'Georgette Embroidered Saree',
            'category': 'Sarees',
            'description': 'Georgette saree featuring hand embroidery with sequins and thread work. Comes with a stylish blouse piece.',
            'base_price': 4500,
            'variants': [
                {'color': 'Navy Blue', 'price_override': None, 'stock': 12},
                {'color': 'Wine Red', 'price_override': 4800, 'stock': 10},
            ],
        },
        {
            'name': 'Cotton Handloom Saree',
            'category': 'Sarees',
            'description': 'Comfortable cotton handloom saree with natural dye and traditional border. Perfect for daily wear and festivals.',
            'base_price': 3000,
            'variants': [
                {'color': 'Natural Dye', 'price_override': None, 'stock': 15},
                {'color': 'Indigo Blue', 'price_override': 3200, 'stock': 14},
            ],
        },
        {
            'name': 'Anarkali Cotton Kurta',
            'category': 'Kurtis',
            'description': 'Flowy Anarkali-style cotton kurta with delicate hand embroidery. Comfortable fit for festive and casual occasions.',
            'base_price': 1800,
            'variants': [
                {'size': 'S', 'price_override': None, 'stock': 20},
                {'size': 'M', 'price_override': None, 'stock': 25},
                {'size': 'L', 'price_override': 1900, 'stock': 22},
                {'size': 'XL', 'price_override': 2000, 'stock': 18},
            ],
        },
        {
            'name': 'Embroidered Rayon Kurti',
            'category': 'Kurtis',
            'description': 'Soft rayon kurti with intricate neck embroidery and side slits. Modern design with traditional charm.',
            'base_price': 2200,
            'variants': [
                {'size': 'M', 'price_override': None, 'stock': 18},
                {'size': 'L', 'price_override': 2400, 'stock': 15},
                {'size': 'XL', 'price_override': 2500, 'stock': 12},
            ],
        },
        {
            'name': 'Straight Cut Silk Kurti',
            'category': 'Kurtis',
            'description': 'Elegant straight-cut silk kurti with subtle zari accents. Perfect for pairing with palazzos or churidar.',
            'base_price': 3500,
            'variants': [
                {'size': 'S', 'price_override': None, 'stock': 10},
                {'size': 'M', 'price_override': None, 'stock': 15},
                {'size': 'L', 'price_override': 3800, 'stock': 12},
            ],
        },
        {
            'name': 'Embroidered Potli Bag',
            'category': 'Accessories',
            'description': 'Handcrafted potli bag with rich embroidery and drawstring closure. Ideal for weddings, gifting, or festive occasions.',
            'base_price': 1500,
            'variants': [
                {'color': 'Red', 'price_override': None, 'stock': 20},
                {'color': 'Green', 'price_override': 1600, 'stock': 18},
                {'color': 'Mustard', 'price_override': 1700, 'stock': 15},
            ],
        },
        {
            'name': 'Juti Mojari Shoes',
            'category': 'Accessories',
            'description': 'Traditional handcrafted mojari jutis with soft leather upper and cushioned sole. Comfortable ethnic footwear.',
            'base_price': 2000,
            'variants': [
                {'size': '6', 'price_override': None, 'stock': 10},
                {'size': '7', 'price_override': None, 'stock': 12},
                {'size': '8', 'price_override': 2200, 'stock': 10},
            ],
        },
        {
            'name': 'Choker with Earrings Set',
            'category': 'Jewelry',
            'description': 'Trendy choker necklace with matching earrings featuring Kundan and pearl detailing. Perfect for Indo-western outfits.',
            'base_price': 4200,
            'variants': [
                {'color': 'Gold Finish', 'price_override': None, 'stock': 10},
                {'color': 'Silver Finish', 'price_override': 4500, 'stock': 8},
            ],
        },
        {
            'name': 'Pure Pashmina Shawl',
            'category': 'Accessories',
            'description': 'Luxuriously soft pure Pashmina shawl with traditional Kashmiri embroidery. Warm and elegant for winter weddings.',
            'base_price': 6000,
            'variants': [
                {'color': 'Cream', 'price_override': None, 'stock': 8},
                {'color': 'Grey', 'price_override': 6500, 'stock': 6},
            ],
        },
    ]
    
    for pdata in products:
        slug = make_slug(pdata['name'])
        existing = Product.query.filter_by(slug=slug).first()
        if not existing:
            product = Product(
                category_id=categories[pdata['category']].id,
                name=pdata['name'],
                slug=slug,
                description=pdata['description'],
                base_price=pdata['base_price'],
                is_active=True,
            )
            db.session.add(product)
            db.session.flush()
            
            for vdata in pdata['variants']:
                size = vdata.get('size')
                color = vdata.get('color')
                sku = slug + '-' + (size or color or '').replace(' ', '-').lower()
                variant = ProductVariant(
                    product_id=product.id,
                    size=size,
                    color=color,
                    sku=sku,
                    price_override=vdata.get('price_override'),
                    stock_quantity=vdata.get('stock', 10),
                )
                db.session.add(variant)
            
            media_items = seed_product_media(product, pdata['name'])
            print(f"  {pdata['name']}: {len(media_items)} media item(s)")
        else:
            ProductMedia.query.filter_by(product_id=existing.id).delete()
            db.session.flush()
            
            media_items = seed_product_media(existing, pdata['name'])
            print(f"  {pdata['name']}: {len(media_items)} media item(s) (refreshed)")
    
    db.session.commit()
    print('Database seeded successfully.')
