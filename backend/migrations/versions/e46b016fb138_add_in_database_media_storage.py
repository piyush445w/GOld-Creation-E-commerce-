"""add_in_database_media_storage

Revision ID: e46b016fb138
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e46b016fb138'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=128), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('country', sa.String(length=2), nullable=True),
        sa.Column('preferred_currency', sa.String(length=3), server_default='INR', nullable=False),
        sa.Column('reset_token', sa.String(length=100), nullable=True),
        sa.Column('reset_token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('role', sa.String(length=20), server_default='customer', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('reset_token')
    )

    op.create_table('categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('image_url', sa.String(length=255), nullable=True),
        sa.Column('is_festival_collection', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )

    op.create_table('currencies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=3), nullable=False),
        sa.Column('symbol', sa.String(length=10), nullable=False),
        sa.Column('exchange_rate_to_inr', sa.Numeric(precision=10, scale=6), server_default='1', nullable=False),
        sa.Column('is_settlement_enabled', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('last_updated', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('site_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('setting_key', sa.String(length=100), nullable=False),
        sa.Column('setting_value', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('setting_key')
    )

    op.create_table('banners',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=True),
        sa.Column('image_url', sa.String(length=255), nullable=True),
        sa.Column('link_url', sa.String(length=255), nullable=True),
        sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('start_date', sa.DateTime(), nullable=True),
        sa.Column('end_date', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('pages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('meta_title', sa.String(length=100), nullable=True),
        sa.Column('meta_description', sa.String(length=255), nullable=True),
        sa.Column('is_published', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )

    op.create_table('navigation_menu',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=False),
        sa.Column('target_url_or_page_slug', sa.String(length=255), nullable=False),
        sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['navigation_menu.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('coupons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('discount_type', sa.String(length=10), nullable=False),
        sa.Column('discount_value', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('min_order_value', sa.Numeric(precision=10, scale=2), server_default='0', nullable=False),
        sa.Column('valid_from', sa.DateTime(), nullable=True),
        sa.Column('valid_to', sa.DateTime(), nullable=True),
        sa.Column('usage_limit', sa.Integer(), nullable=True),
        sa.Column('times_used', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('applies_to_category_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['applies_to_category_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )

    op.create_table('newsletter_subscribers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('subscribed_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )

    op.create_table('products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('base_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('sku', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('festival_tag', sa.String(length=100), nullable=True),
        sa.Column('meta_title', sa.String(length=100), nullable=True),
        sa.Column('meta_description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
        sa.UniqueConstraint('sku')
    )

    op.create_table('addresses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=50), nullable=True),
        sa.Column('line1', sa.String(length=200), nullable=False),
        sa.Column('line2', sa.String(length=200), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=False),
        sa.Column('state', sa.String(length=100), nullable=False),
        sa.Column('country', sa.String(length=2), nullable=False),
        sa.Column('postal_code', sa.String(length=20), nullable=False),
        sa.Column('is_default', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('product_variants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('size', sa.String(length=20), nullable=True),
        sa.Column('color', sa.String(length=50), nullable=True),
        sa.Column('sku', sa.String(length=100), nullable=True),
        sa.Column('price_override', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('stock_quantity', sa.Integer(), server_default='0', nullable=False),
        sa.Column('image_url', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('product_media',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('media_type', sa.String(length=10), nullable=False),
        sa.Column('media_url', sa.String(length=255), nullable=False),
        sa.Column('thumbnail_url', sa.String(length=255), nullable=True),
        sa.Column('mime_type', sa.String(length=50), nullable=True),
        sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_primary', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('is_approved', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('cart_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('guest_session_id', sa.String(length=100), nullable=True),
        sa.Column('product_variant_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), server_default='1', nullable=False),
        sa.Column('added_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['product_variant_id'], ['product_variants.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('wishlist_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('added_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('page_media',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('page_id', sa.Integer(), nullable=False),
        sa.Column('media_type', sa.String(length=50), server_default='image', nullable=False),
        sa.Column('media_url', sa.String(length=255), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_primary', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.Column('media_data', sa.LargeBinary(length=4294967295), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('original_filename', sa.String(length=255), nullable=True),
        sa.Column('checksum', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('order_number', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('subtotal', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('discount_amount', sa.Numeric(precision=10, scale=2), server_default='0', nullable=False),
        sa.Column('shipping_fee', sa.Numeric(precision=10, scale=2), server_default='0', nullable=False),
        sa.Column('total', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('display_currency', sa.String(length=3), server_default='INR', nullable=False),
        sa.Column('charged_currency', sa.String(length=3), server_default='INR', nullable=False),
        sa.Column('charged_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('exchange_rate_used', sa.Numeric(precision=10, scale=6), server_default='1', nullable=False),
        sa.Column('payment_method', sa.String(length=50), nullable=True),
        sa.Column('payment_status', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('shipping_address_id', sa.Integer(), nullable=False),
        sa.Column('tracking_number', sa.String(length=100), nullable=True),
        sa.Column('placed_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['shipping_address_id'], ['addresses.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_number')
    )

    op.create_table('order_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('product_variant_id', sa.Integer(), nullable=False),
        sa.Column('product_name_snapshot', sa.String(length=200), nullable=False),
        sa.Column('unit_price_snapshot', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('subtotal', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['product_variant_id'], ['product_variants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.add_column('banners', sa.Column('banner_data', sa.LargeBinary(length=4294967295), nullable=True))
    op.add_column('banners', sa.Column('checksum', sa.String(length=64), nullable=True))
    op.add_column('banners', sa.Column('file_size', sa.BigInteger(), nullable=True))
    op.add_column('banners', sa.Column('mime_type', sa.String(length=50), nullable=True))

    op.add_column('product_media', sa.Column('checksum', sa.String(length=64), nullable=True))
    op.add_column('product_media', sa.Column('file_size', sa.BigInteger(), nullable=True))
    op.add_column('product_media', sa.Column('media_data', sa.LargeBinary(length=4294967295), nullable=True))
    op.add_column('product_media', sa.Column('original_filename', sa.String(length=255), nullable=True))
    op.add_column('product_media', sa.Column('thumbnail_data', sa.LargeBinary(length=4294967295), nullable=True))

    op.add_column('product_variants', sa.Column('variant_image_data', sa.LargeBinary(length=4294967295), nullable=True))
    op.add_column('product_variants', sa.Column('variant_image_mime', sa.String(length=50), nullable=True))

    op.create_unique_constraint('uq_reviews_product_user', 'reviews', ['product_id', 'user_id'])

    op.add_column('wishlist_items', sa.Column('guest_session_id', sa.String(length=100), nullable=True))
    op.alter_column('wishlist_items', 'user_id', existing_type=sa.Integer(), nullable=True)


def downgrade():
    op.alter_column('wishlist_items', 'user_id', existing_type=sa.Integer(), nullable=False)
    op.drop_column('wishlist_items', 'guest_session_id')

    op.drop_constraint('uq_reviews_product_user', 'reviews', type_='unique')

    op.drop_column('product_variants', 'variant_image_mime')
    op.drop_column('product_variants', 'variant_image_data')

    op.drop_column('product_media', 'thumbnail_data')
    op.drop_column('product_media', 'original_filename')
    op.drop_column('product_media', 'file_size')
    op.drop_column('product_media', 'media_data')
    op.drop_column('product_media', 'checksum')

    op.drop_column('banners', 'mime_type')
    op.drop_column('banners', 'file_size')
    op.drop_column('banners', 'checksum')
    op.drop_column('banners', 'banner_data')

    op.drop_table('order_items')
    op.drop_table('orders')
    op.drop_table('page_media')
    op.drop_table('wishlist_items')
    op.drop_table('cart_items')
    op.drop_table('reviews')
    op.drop_table('product_media')
    op.drop_table('product_variants')
    op.drop_table('addresses')
    op.drop_table('products')
    op.drop_table('newsletter_subscribers')
    op.drop_table('coupons')
    op.drop_table('navigation_menu')
    op.drop_table('pages')
    op.drop_table('banners')
    op.drop_table('site_settings')
    op.drop_table('currencies')
    op.drop_table('categories')
    op.drop_table('users')
