import asyncio
import sys
import os

# Add current working directory to path (assuming run from backend root)
sys.path.append(os.getcwd())

from app.core.database import async_session
from app.models.user import User
from app.core.auth import hash_password
from sqlalchemy import select

async def create_admin():
    async with async_session() as db:
        # Check if admin exists
        result = await db.execute(select(User).where(User.username == "admin"))
        user = result.scalar_one_or_none()
        
        if user:
            print("Admin user 'admin' already exists.")
            # Update password just in case
            user.hashed_password = hash_password("admin1234")
            user.is_active = True
            await db.commit()
            print("Password reset to 'admin1234'.")
        else:
            print("Creating admin user...")
            new_user = User(
                username="admin",
                hashed_password=hash_password("admin1234"),
                full_name="System Administrator",
                role="admin",
                is_active=True,
                privacy_consented=True
            )
            db.add(new_user)
            await db.commit()
            print("Admin user created.")
            print("Username: admin")
            print("Password: admin1234")

if __name__ == "__main__":
    asyncio.run(create_admin())
