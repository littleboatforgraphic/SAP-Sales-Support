"""
Role-based routing and notification helper functions.

This module provides utilities for:
- Getting staff by role
- Sending notifications to specific roles
- Managing staff role assignments
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from database import StaffAllowlistEntry, StaffRole, Role


def get_staff_by_role(db: Session, role: Role) -> List[StaffAllowlistEntry]:
    """
    Get all active staff members with a specific role.

    Args:
        db: Database session
        role: Role to filter by

    Returns:
        List of staff members with the specified role
    """
    return db.query(StaffAllowlistEntry).join(StaffRole).filter(
        StaffRole.role == role,
        StaffAllowlistEntry.active == True
    ).all()


def get_staff_by_roles(db: Session, roles: List[Role]) -> List[StaffAllowlistEntry]:
    """
    Get all active staff members with any of the specified roles.

    Args:
        db: Database session
        roles: List of roles to filter by

    Returns:
        List of staff members with any of the specified roles
    """
    return db.query(StaffAllowlistEntry).join(StaffRole).filter(
        StaffRole.role.in_(roles),
        StaffAllowlistEntry.active == True
    ).all()


def get_staff_by_telegram_id(db: Session, telegram_user_id: str) -> Optional[StaffAllowlistEntry]:
    """
    Get a staff member by Telegram user ID.

    Args:
        db: Database session
        telegram_user_id: Telegram user ID

    Returns:
        Staff member or None
    """
    return db.query(StaffAllowlistEntry).filter(
        StaffAllowlistEntry.telegram_user_id == telegram_user_id,
        StaffAllowlistEntry.active == True
    ).first()


def get_staff_roles(db: Session, staff_id: int) -> List[Role]:
    """
    Get all roles for a staff member.

    Args:
        db: Database session
        staff_id: Staff ID

    Returns:
        List of roles
    """
    roles = db.query(StaffRole.role).filter(
        StaffRole.staff_id == staff_id
    ).all()
    return [r[0] for r in roles]


def add_role_to_staff(db: Session, staff_id: int, role: Role) -> bool:
    """
    Add a role to a staff member.

    Args:
        db: Database session
        staff_id: Staff ID
        role: Role to add

    Returns:
        True if successful, False if role already exists
    """
    # Check if role already exists
    existing = db.query(StaffRole).filter(
        StaffRole.staff_id == staff_id,
        StaffRole.role == role
    ).first()

    if existing:
        return False

    # Add new role
    new_role = StaffRole(staff_id=staff_id, role=role)
    db.add(new_role)
    db.commit()
    return True


def remove_role_from_staff(db: Session, staff_id: int, role: Role) -> bool:
    """
    Remove a role from a staff member.

    Args:
        db: Database session
        staff_id: Staff ID
        role: Role to remove

    Returns:
        True if successful, False if role didn't exist
    """
    existing = db.query(StaffRole).filter(
        StaffRole.staff_id == staff_id,
        StaffRole.role == role
    ).first()

    if not existing:
        return False

    db.delete(existing)
    db.commit()
    return True


def has_role(db: Session, staff_id: int, role: Role) -> bool:
    """
    Check if a staff member has a specific role.

    Args:
        db: Database session
        staff_id: Staff ID
        role: Role to check

    Returns:
        True if staff has the role
    """
    return db.query(StaffRole).filter(
        StaffRole.staff_id == staff_id,
        StaffRole.role == role
    ).first() is not None


def get_admin_staff(db: Session) -> List[StaffAllowlistEntry]:
    """
    Get all staff with Admin role.

    Args:
        db: Database session

    Returns:
        List of admin staff members
    """
    return get_staff_by_role(db, Role.ADMIN)
