# Role-Based Staff Management

## Overview

The system now supports role-based staff management to handle multiple internal departments interacting via Telegram. Staff can have multiple roles, and notifications are routed based on roles.

## Roles

The system supports the following roles:

- **Admin** - Administrative staff who receive email order notifications and can view admin endpoints
- **Sales** - Sales team members
- **Finance** - Finance/Accounts team members
- **Logistics** - Warehouse/Logistics team members

## Database Schema

### StaffAllowlistEntry
Main staff table with Telegram user ID and basic info.

```python
class StaffAllowlistEntry(Base):
    id: Integer
    phone_number: String (unique, optional)
    telegram_user_id: String (unique, optional)
    name: String
    active: Boolean
    added_at: DateTime
    added_by: String
    roles: List[StaffRole] (relationship)
```

### StaffRole
Join table for many-to-many relationship between staff and roles.

```python
class StaffRole(Base):
    id: Integer
    staff_id: Integer (FK to StaffAllowlistEntry)
    role: Enum (ADMIN, SALES, FINANCE, LOGISTICS)
    assigned_at: DateTime
    staff: StaffAllowlistEntry (relationship)
```

**Key Feature**: One staff can have multiple roles (e.g., both Finance and Admin).

## Role-Based Routing

### Current Implementation

**Email Order Notifications** → Send to all staff with **Admin** role
- When an email PO is processed and a draft is created in AutoCount
- Notification is sent via Telegram to all admin staff
- Includes scenario, PO number, customer name, and AutoCount draft number

**Individual Queries** → Answer to the individual
- When a staff member asks a question via Telegram
- The response goes back to that individual only
- No role-based routing for queries (per your requirement)

**Admin API Access** → Requires **Admin** role
- Viewing draft lists, details, and stats
- Only staff with Admin role can access admin endpoints

### Future Enhancements (KIV)

- Role-based query routing (e.g., stock questions → Logistics team)
- Escalation workflows (unanswered queries → escalate to Admin)
- Report routing (send reports to specific roles)
- Role-based permissions (different access levels per role)

## Usage

### Adding Staff with Roles

**Using setup script:**
```bash
# Add staff with single role (default: admin)
python setup_test_deployment.py --add-staff 123456789 --name "John Doe"

# Add staff with multiple roles
python setup_test_deployment.py --add-staff 123456789 --name "John Doe" --roles "admin,finance"

# Add staff with Sales role
python setup_test_deployment.py --add-staff 123456789 --name "Jane Smith" --roles "sales"

# Add staff with Logistics role
python setup_test_deployment.py --add-staff 123456789 --name "Bob Wilson" --roles "logistics"
```

**Using role_helpers.py programmatically:**
```python
from role_helpers import add_role_to_staff, remove_role_from_staff, has_role

# Add a role
add_role_to_staff(db, staff_id=1, Role.ADMIN)

# Remove a role
remove_role_from_staff(db, staff_id=1, Role.SALES)

# Check if staff has a role
if has_role(db, staff_id=1, Role.ADMIN):
    print("User is an admin")
```

### Getting Staff by Role

```python
from role_helpers import get_staff_by_role, get_staff_by_roles

# Get all admin staff
admin_staff = get_staff_by_role(db, Role.ADMIN)

# Get staff with Finance or Admin roles
staff = get_staff_by_roles(db, [Role.FINANCE, Role.ADMIN])

# Get staff by Telegram ID
staff = get_staff_by_telegram_id(db, "123456789")

# Get all roles for a staff member
roles = get_staff_roles(db, staff_id=1)
```

## Email Order Notification Flow

```
Email PO Received
    ↓
Extracted & Matched
    ↓
Draft Created in AutoCount
    ↓
get_admin_staff(db) → Get all staff with Admin role
    ↓
For each admin staff:
    - Send Telegram notification
    - Include draft details
    - Log notification sent
```

**Example Notification to Admin:**
```
📧 CONFIRMED_PO: ABC Trading Sdn Bhd (PO: PO-2026-001)
Draft: ARInvoice #INV-2026-00123
Status: AR Invoice draft created: INV-2026-00123
```

## Admin API Access Control

All admin endpoints require the user to have the **Admin** role:

- `GET /api/v1/admin/drafts` - View all email order drafts
- `GET /api/v1/admin/draft-details` - View draft details
- `GET /api/v1/admin/stats` - View processing statistics

**Access check:**
```python
def verify_staff_access(user_id: str, db: Session) -> bool:
    staff = db.query(StaffAllowlistEntry).filter(
        StaffAllowlistEntry.telegram_user_id == user_id,
        StaffAllowlistEntry.active == True
    ).first()

    if not staff:
        return False

    # Must have Admin role
    return has_role(db, staff.id, Role.ADMIN)
```

## Migration from Old Schema

The old schema had a single `role` column on `StaffAllowlistEntry`. The new schema:

1. **Removed** the `role` column from `StaffAllowlistEntry`
2. **Added** a separate `StaffRole` table for many-to-many relationships
3. **Allows** multiple roles per staff member

**Migration steps:**
1. Delete old database (SQLite) or run migration script
2. Run `init_database()` to create new schema
3. Re-add staff members with their roles using the setup script

## Example Staff Configurations

### Sales Manager with Admin Access
```bash
python setup_test_deployment.py \
  --add-staff 123456789 \
  --name "Sales Manager" \
  --roles "admin,sales"
```

This staff can:
- Receive email order notifications (Admin role)
- View admin endpoints (Admin role)
- Ask questions via Telegram (individual response)

### Finance Team Member
```bash
python setup_test_deployment.py \
  --add-staff 987654321 \
  --name "Finance Officer" \
  --roles "finance"
```

This staff can:
- Ask questions via Telegram (individual response)
- Future: Receive finance-related notifications (when implemented)

### Logistics Team Member
```bash
python setup_test_deployment.py \
  --add-staff 555555555 \
  --name "Warehouse Manager" \
  --roles "logistics"
```

This staff can:
- Ask questions via Telegram (individual response)
- Future: Receive delivery order notifications (when implemented)

## Testing

### Add Test Staff with Admin Role
```bash
python setup_test_deployment.py --add-staff YOUR_TELEGRAM_ID --roles "admin"
```

### Send Test Email
```bash
curl -X POST http://localhost:8000/api/v1/webhook/email-po/mock \
  -H "X-Email-Secret-Token: your_secret"
```

### Verify Notification Received
Check your Telegram - you should receive a notification if you have the Admin role.

### Verify Admin API Access
```bash
curl "http://localhost:8000/api/v1/admin/drafts?user_id=YOUR_TELEGRAM_ID"
```

Should return draft list if you have Admin role, 403 otherwise.

## Role Helpers API

### `get_staff_by_role(db, role)`
Get all active staff with a specific role.

### `get_staff_by_roles(db, roles)`
Get all active staff with any of the specified roles.

### `get_staff_by_telegram_id(db, telegram_user_id)`
Get a staff member by Telegram user ID.

### `get_staff_roles(db, staff_id)`
Get all roles for a staff member.

### `add_role_to_staff(db, staff_id, role)`
Add a role to a staff member. Returns False if role already exists.

### `remove_role_from_staff(db, staff_id, role)`
Remove a role from a staff member. Returns False if role didn't exist.

### `has_role(db, staff_id, role)`
Check if a staff member has a specific role.

### `get_admin_staff(db)`
Get all staff with Admin role (convenience function).

## Security Considerations

1. **Admin Role Required for Critical Actions**
   - Only Admin role can view admin endpoints
   - Email order notifications only go to Admin role
   - Prevents unauthorized access to sensitive data

2. **Role Assignment**
   - Roles are assigned via setup script or database
   - Staff can have multiple roles
   - Role changes require database update

3. **Individual Query Routing**
   - Individual staff ask questions → answer to individual
   - No role-based routing for queries (as requested)
   - Prevents confusion and ensures accountability

4. **Future Escalation**
   - Escalation workflows KIV for future
   - Can add timeout-based escalation later
   - Can add manual escalation commands later

## Troubleshooting

### Issue: Not receiving email notifications
- Verify you have the Admin role
- Check your Telegram user ID is correct
- Ensure Telegram bot is working
- Check logs for notification errors

### Issue: Cannot access admin endpoints
- Verify you have the Admin role
- Check your Telegram user ID matches the database
- Ensure staff entry is active

### Issue: Role not being added
- Check role name is valid (admin, sales, finance, logistics)
- Verify database connection
- Check for duplicate staff_id + role combination

### Issue: Old role column still exists
- Delete old database file (SQLite)
- Run `init_database()` to create new schema
- Re-add staff with new role system
