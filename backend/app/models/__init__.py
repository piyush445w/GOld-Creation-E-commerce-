"""Model package aggregator for Gold Creation.

Re-exports every SQLAlchemy model class from its own module so the rest of the
app can simply ``from app.models import User, Product, Order`` and, crucially,
so that importing ``app.models`` registers every table on the shared
``db.metadata`` before ``db.create_all()`` or Alembic runs.
"""

# Identity, catalogue, and checkout models, imported in dependency order.
from app.models.user import User
from app.models.address import Address
from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.product_media import ProductMedia
from app.models.category_media import CategoryMedia
from app.models.cart import CartItem
from app.models.wishlist import WishlistItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.coupon import Coupon
from app.models.page import Page
from app.models.page_media import PageMedia
from app.models.site_setting import SiteSetting
from app.models.site_asset import SiteAsset
# Presentation/content models (banners, menus, CMS pages, site settings, currency).
from app.models.banner import Banner
from app.models.navigation_menu import NavigationMenu
from app.models.currency import Currency
from app.models.review import Review
