FINANCE DATA PROCESSING AND ACCESS CONTROL BACKEND
===================================================

A robust, production-grade REST API backend for a finance dashboard system. Built with FastAPI, it implements strict Role-Based Access Control (RBAC), comprehensive financial record management, and advanced aggregated analytics endpoints.


TABLE OF CONTENTS
-----------------
1. Overview
2. Tech Stack
3. System Architecture
4. Key Features
5. Getting Started
6. Access Control Matrix
7. API Documentation
8. Running Tests
9. Design Decisions & Trade-offs
10. Future Enhancements


1. OVERVIEW
-----------
This backend serves as the foundation for a financial dashboard application. It allows different types of users (Viewers, Analysts, and Admins) to interact with financial data securely based on their assigned roles. The system handles user management, income/expense tracking, soft-deletion of records, and complex data aggregations for dashboard visualizations.


2. TECH STACK
-------------
- Language: Python 3.12+
- Framework: FastAPI
- Database: SQLite (via SQLAlchemy ORM)
- Auth: JWT (python-jose) + Bcrypt (passlib)
- Validation: Pydantic v2
- Server: Uvicorn


3. SYSTEM ARCHITECTURE
----------------------
The application follows a strict Separation of Concerns architecture across 5 core files:

- models.py (Data Layer): SQLAlchemy ORM models (User, FinancialRecord), Pydantic schemas for request/response validation, database engine configuration, and enumerations.

- auth.py (Security Layer): JWT generation/verification, password hashing, and FastAPI dependency injection functions for authentication (get_current_user) and authorization (require_role).

- services.py (Business Logic Layer): Core domain operations. Contains UserService, RecordService, and DashboardService. This layer enforces business rules, handles complex SQLAlchemy aggregations, and keeps routes clean.

- routes.py (HTTP Layer): API endpoint definitions. Wires HTTP requests to Pydantic schemas, passes them to Services, and returns JSON responses. Handles no business logic.

- main.py (Bootstrap Layer): FastAPI app initialization, CORS middleware, request timing/logging middleware, global exception handlers, database table creation, and admin user seeding.


4. KEY FEATURES
---------------
- Hierarchical RBAC: Role hierarchy (Viewer < Analyst < Admin) allows graceful permission escalation.
- JWT Authentication: Secure, stateless token-based auth with configurable expiration.
- Advanced Aggregations: Database-level grouping and conditional sums (using SQLAlchemy case expressions) for category breakdowns and monthly/weekly trends.
- Soft Deletes: Financial records are never hard-deleted, preserving data integrity and audit trails.
- Rich Filtering: Query parameters for type, category, date ranges, and full-text search on descriptions.
- Global Exception Handling: Custom middleware catches validation errors and unhandled exceptions, returning clean, standardized JSON error responses.
- Automated Seeding: Automatically creates a default Admin user on startup to prevent lockouts.


5. GETTING STARTED
------------------
Prerequisites:
- Python 3.12 or higher installed.

Installation Steps:
1. Clone or download the project files into a directory.
2. Install dependencies: pip install -r requirements.txt
3. Run the server: python main.py
4. Access the API:
   - Interactive Docs (Swagger UI): http://localhost:8000/docs
   - Alternative Docs (ReDoc): http://localhost:8000/redoc

Default Admin Credentials:
Upon first startup, the database is initialized with an Admin user:
- Email: admin@finance.com
- Password: admin123


6. ACCESS CONTROL MATRIX
-------------------------
Defines exactly what each role is permitted to do.

Authentication:
- Login: Viewer (Yes), Analyst (Yes), Admin (Yes)
- Register New Users: Viewer (No), Analyst (No), Admin (Yes)
- View Own Profile: Viewer (Yes), Analyst (Yes), Admin (Yes)

User Management:
- List All Users: Viewer (No), Analyst (No), Admin (Yes)
- Update User Roles: Viewer (No), Analyst (No), Admin (Yes)
- Activate/Deactivate Users: Viewer (No), Analyst (No), Admin (Yes)

Financial Records:
- View Records (List/Filter): Viewer (No), Analyst (Yes), Admin (Yes)
- Create Record: Viewer (No), Analyst (Yes), Admin (Yes)
- Update Record: Viewer (No), Analyst (No), Admin (Yes)
- Soft-Delete Record: Viewer (No), Analyst (No), Admin (Yes)
- View Soft-Deleted Records: Viewer (No), Analyst (No), Admin (Yes)

Dashboard Analytics:
- Summary (Income/Expense/Balance): Viewer (Yes), Analyst (Yes), Admin (Yes)
- Category Breakdown: Viewer (Yes), Analyst (Yes), Admin (Yes)
- Recent Activity: Viewer (Yes), Analyst (Yes), Admin (Yes)
- Trends (Monthly/Weekly): Viewer (No), Analyst (Yes), Admin (Yes)


7. API DOCUMENTATION
--------------------
Base URL: http://localhost:8000
Note: All secured endpoints require an Authorization header formatted as: Bearer <token>

LOGIN
Endpoint: POST /api/auth/login
Body: {"email": "admin@finance.com", "password": "admin123"}

REGISTER USER (Admin Only)
Endpoint: POST /api/auth/register
Body: {"email": "analyst@test.com", "name": "John Doe", "password": "password123", "role": "analyst"}

TOGGLE USER STATUS (Admin Only)
Endpoint: PATCH /api/users/{user_id}/status

UPDATE USER ROLE (Admin Only)
Endpoint: PUT /api/users/{user_id}/role
Body: {"role": "viewer"}

CREATE RECORD (Analyst+)
Endpoint: POST /api/records
Body: {"amount": 1500.50, "type": "income", "category": "Salary", "record_date": "2024-10-25", "description": "October payroll"}

LIST & FILTER RECORDS (Analyst+)
Endpoint: GET /api/records?type=expense&category=Housing&date_from=2024-01-01&page=1&page_size=20

SOFT DELETE RECORD (Admin Only)
Endpoint: DELETE /api/records/{record_id}

SUMMARY
Endpoint: GET /api/dashboard/summary
Returns: total_income, total_expenses, net_balance, total_records

CATEGORY BREAKDOWN
Endpoint: GET /api/dashboard/categories
Returns: Array of categories with total amount, count of transactions, and type.

TRENDS (Analyst+)
Endpoint: GET /api/dashboard/trends?period_type=monthly&months=6
Returns: Array of time periods with income, expenses, and net values.


8. RUNNING TESTS
----------------
A fully automated test suite is provided in test.py. It spins up its own server instance, runs 99 tests covering all CRUD operations, RBAC enforcement, validation errors, and analytics accuracy, and then shuts down cleanly.

To run: python test.py

Expected Output:
Server starts...
99 tests run...
Total: 99 | Passed: 99 | Failed: 0
Success Rate: 100.0%


9. DESIGN DECISIONS & TRADE-OFFS
---------------------------------
To ensure clarity and maintainability, several deliberate architectural and technical choices were made:

1. SQLite over Postgres: 
Decision: Used SQLite for zero-configuration local setup. 
Trade-off: Lacks concurrent write capabilities of Postgres. The models.py engine configuration can be swapped to Postgres by changing the DATABASE_URL without altering any business logic.
   
2. Float over Decimal for Amounts: 
Decision: Used SQL Float and Python float for financial amounts. 
Trade-off: Can introduce minor floating-point precision issues. In a true production system handling real currency, Numeric(10, 2) (Decimal) would be strictly required.

3. Global Dashboard View: 
Decision: Dashboard summaries aggregate data from all users across the system. 
Trade-off: Multi-tenant or personal dashboards would require passing a user_id filter to the DashboardService. This was kept global for simplicity.

4. Free-Text Categories: 
Decision: Categories are string fields normalized via Pydantic (Title Case) rather than a relational lookup table. 
Trade-off: Slight risk of duplication (e.g., "Food" vs "Foods"). Avoided a lookup table to minimize schema complexity and joins, keeping the API flat and fast.

5. Middleware via BaseHTTPMiddleware: 
Decision: Used Starlette's BaseHTTPMiddleware for request timing and logging. 
Trade-off: Has slight overhead compared to pure ASGI middleware because it wraps the request/response cycle. However, it provides direct access to the FastAPI Request object, making it much cleaner to extract user context.


10. FUTURE ENHANCEMENTS
-----------------------
If this system were to be promoted to a production environment, the following steps would be taken:

- Decimal Precision: Migrate amount columns to SQLAlchemy Numeric(12, 2).
- Refresh Tokens: Implement a refresh token flow to allow long-lived sessions without compromising security.
- Rate Limiting: Add slowapi to prevent brute-force attacks on the login endpoint.
- Pagination Cursors: Replace offset-based pagination with cursor-based pagination for faster queries on large datasets.
- Export Endpoints: CSV/PDF exports for financial records and summaries.
- Database Migrations: Integrate Alembic for version-controlled schema migrations instead of creating tables directly on startup.