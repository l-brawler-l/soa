"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-04 17:28:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE user_role AS ENUM ('USER', 'SELLER', 'ADMIN');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE product_status AS ENUM ('ACTIVE', 'INACTIVE', 'ARCHIVED');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE order_status AS ENUM ('CREATED', 'PAYMENT_PENDING', 'PAID', 'SHIPPED', 'COMPLETED', 'CANCELED');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE discount_type AS ENUM ('PERCENTAGE', 'FIXED_AMOUNT');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE operation_type AS ENUM ('CREATE_ORDER', 'UPDATE_ORDER');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Create tables using raw SQL to avoid enum creation issues
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) NOT NULL UNIQUE,
            hashed_password VARCHAR(255) NOT NULL,
            role user_role NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            description VARCHAR(4000),
            price DECIMAL(12,2) NOT NULL CHECK (price > 0),
            stock INTEGER NOT NULL CHECK (stock >= 0),
            category VARCHAR(100) NOT NULL,
            status product_status NOT NULL,
            seller_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS ix_products_status ON products(status);
        CREATE INDEX IF NOT EXISTS ix_products_category ON products(category);
        CREATE INDEX IF NOT EXISTS ix_products_seller_id ON products(seller_id);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            code VARCHAR(20) NOT NULL UNIQUE,
            discount_type discount_type NOT NULL,
            discount_value DECIMAL(12,2) NOT NULL CHECK (discount_value > 0),
            min_order_amount DECIMAL(12,2) NOT NULL CHECK (min_order_amount >= 0),
            max_uses INTEGER NOT NULL CHECK (max_uses > 0),
            current_uses INTEGER NOT NULL DEFAULT 0 CHECK (current_uses >= 0),
            valid_from TIMESTAMP WITH TIME ZONE NOT NULL,
            valid_until TIMESTAMP WITH TIME ZONE NOT NULL,
            active BOOLEAN NOT NULL DEFAULT true,
            CONSTRAINT check_current_uses_not_exceed_max CHECK (current_uses <= max_uses)
        );

        CREATE INDEX IF NOT EXISTS ix_promo_codes_code ON promo_codes(code);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status order_status NOT NULL,
            promo_code_id UUID REFERENCES promo_codes(id) ON DELETE SET NULL,
            total_amount DECIMAL(12,2) NOT NULL CHECK (total_amount >= 0),
            discount_amount DECIMAL(12,2) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS ix_orders_user_id ON orders(user_id);
        CREATE INDEX IF NOT EXISTS ix_orders_status ON orders(status);
        CREATE INDEX IF NOT EXISTS ix_orders_user_status ON orders(user_id, status);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            quantity INTEGER NOT NULL CHECK (quantity > 0),
            price_at_order DECIMAL(12,2) NOT NULL CHECK (price_at_order > 0)
        );

        CREATE INDEX IF NOT EXISTS ix_order_items_order_id ON order_items(order_id);
        CREATE INDEX IF NOT EXISTS ix_order_items_product_id ON order_items(product_id);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_operations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            operation_type operation_type NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS ix_user_operations_user_id ON user_operations(user_id);
        CREATE INDEX IF NOT EXISTS ix_user_operations_user_type ON user_operations(user_id, operation_type);
    """)

    # Create triggers for updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    op.execute("""
        CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_products_updated_at BEFORE UPDATE ON products
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)

    op.execute("""
        CREATE TRIGGER update_orders_updated_at BEFORE UPDATE ON orders
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS update_orders_updated_at ON orders")
    op.execute("DROP TRIGGER IF EXISTS update_products_updated_at ON products")
    op.execute("DROP TRIGGER IF EXISTS update_users_updated_at ON users")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")

    # Drop tables
    op.execute("DROP TABLE IF EXISTS user_operations CASCADE")
    op.execute("DROP TABLE IF EXISTS order_items CASCADE")
    op.execute("DROP TABLE IF EXISTS orders CASCADE")
    op.execute("DROP TABLE IF EXISTS promo_codes CASCADE")
    op.execute("DROP TABLE IF EXISTS products CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS operation_type")
    op.execute("DROP TYPE IF EXISTS discount_type")
    op.execute("DROP TYPE IF EXISTS order_status")
    op.execute("DROP TYPE IF EXISTS product_status")
    op.execute("DROP TYPE IF EXISTS user_role")
