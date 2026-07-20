---
name: python-engineering-process
description: Use when writing, reviewing, refactoring, or simplifying Python backend/API code (FastAPI, Pydantic, SQLAlchemy, services, tests). Encodes a repeatable engineering process, not project-specific logic. Triggers on "write a FastAPI endpoint", "create a Pydantic schema", "add a service", "handle exceptions", "review this Python module", "simplify this code", "refactor this function".
---

# Python (FastAPI / Backend) Engineering Process

This is a synthesized reference of current Python backend practice (FastAPI/Pydantic v2/SQLAlchemy 2.0 conventions, PEP 8) — not a transcript of one project's decisions. Use it as the default process for Python API/backend work. If a codebase already has an established, working convention, match that over this skill.

Each rule below states: the rule, why it exists, when to apply it, when not to, and one concrete example.

## 1. Python Coding Style & Naming
- **Rule:** `snake_case` for functions/variables, `PascalCase` for classes, type hints on every public function signature.
- **Why:** Python's dynamic typing means the function signature is the only contract a reader (and a type checker) has; untyped code forces readers to trace call sites to know what a function accepts.
- **Apply when:** writing or reviewing any function, method, or class used outside its own module.
- **Skip when:** a short-lived private lambda/local closure where the type is obvious from one line above it.
- **Example:** `def calc(u, o):` rewritten as `def calculate_order_total(user: User, order: Order) -> Decimal:`.

## 2. Project Structure & Package Organization
- **Rule:** use a `src/` layout with packages split by domain (`routers/`, `schemas/`, `models/`, `services/`, `repositories/`) for one service; don't nest by type for every tiny helper.
- **Why:** a `src/` layout prevents accidentally importing the uninstalled package from the working directory; splitting by domain keeps a 50+ endpoint API navigable the way a flat `main.py` cannot.
- **Apply when:** starting a FastAPI service, or a single-file app grows past ~5 endpoints.
- **Skip when:** a genuinely small script or a single-endpoint prototype — one file is fine until it isn't.
- **Example:** `app/routers/orders.py`, `app/schemas/order.py`, `app/services/order_service.py`, `app/repositories/order_repository.py` instead of one 800-line `main.py`.

## 3. Dependency Injection
- **Rule:** pass collaborators as constructor/function parameters (FastAPI `Depends()` for request-scoped dependencies); never reach for a module-level global or mutable singleton.
- **Why:** `Depends()`-injected services can be overridden in tests (`app.dependency_overrides`) without patching modules; globals make tests order-dependent and hide what a function actually needs.
- **Apply when:** a route or service needs a DB session, an external client, or another service.
- **Skip when:** a pure, stateless utility function (e.g. `slugify(text: str) -> str`) — injecting a dependency into something with no side effects is ceremony.
- **Example:**
```python
# Before: module-level singleton
db_session = SessionLocal()
def get_order(order_id: int):
    return db_session.query(Order).get(order_id)

# After: request-scoped dependency
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/orders/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    ...
```

## 4. SOLID in Practice (Pythonic)
- **Rule:** apply SRP by keeping one module/function focused on one job; apply DIP with `typing.Protocol` structural typing instead of building abstract base class hierarchies "just in case."
- **Why:** Python's duck typing already gives you DIP for free — a `Protocol` documents the expected shape without forcing every implementation to inherit from a common ABC.
- **Apply when:** a function mixes validation, persistence, and notification, or a service depends on a concrete client class it should depend on abstractly for testing.
- **Skip when:** there's only one implementation and no test double is needed — a plain concrete dependency is simpler than a `Protocol` with one implementer.
- **Example:** `NotificationService` depended on a concrete `SmtpClient`; changed to depend on a `Protocol` with a `send(to: str, body: str) -> None` method so tests can pass a fake without a real ABC hierarchy.

## 5. Design Patterns Actually Used
- **Rule:** prefer plain functions, dataclasses, and dict-based dispatch over Java-style pattern classes (Factory/Strategy/Singleton objects).
- **Why:** Python has first-class functions and modules as singletons already; wrapping a single `if/elif` chain in a `StrategyFactory` class re-implements what a `dict[str, Callable]` does in three lines.
- **Apply when:** genuinely dispatching between 3+ interchangeable behaviors selected at runtime.
- **Skip when:** a simple `if/elif` with 2 branches reads fine — don't introduce a registry pattern for two cases.
- **Example:** payment handling replaced a `PaymentStrategyFactory` class hierarchy with `PAYMENT_HANDLERS: dict[str, Callable[[Order], None]] = {"card": handle_card, "upi": handle_upi}`.

## 6. DTO vs Domain Model Separation
- **Rule:** define separate Pydantic schemas for input (`OrderCreate`) and output (`OrderResponse`); never return a SQLAlchemy ORM instance directly from a route.
- **Why:** returning the ORM model directly leaks lazy-loaded relationships and internal columns (password hashes, internal flags) into the API response; separate input/output schemas also stop clients from setting server-only fields like `id` or `created_at`.
- **Apply when:** any data crosses a route boundary, in either direction.
- **Skip when:** an internal, same-process function passes an ORM object to another service function — that's fine without a schema.
- **Example:**
```python
class OrderCreate(BaseModel):
    customer_id: int
    items: list[OrderItemCreate]

class OrderResponse(BaseModel):
    id: int
    status: OrderStatus
    total: Decimal
    model_config = ConfigDict(from_attributes=True)

@router.post("/orders", response_model=OrderResponse)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    order = order_service.create_order(db, payload)
    return order  # OrderResponse validates/filters the ORM object automatically
```

## 7. Repository Pattern
- **Rule:** wrap SQLAlchemy queries behind small repository functions/classes only when you need to swap data sources or unit-test service logic without a database.
- **Why:** a repository layer earns its cost when it lets `OrderServiceTest` run against a fake in-memory repository; if the service always talks straight to SQLAlchemy and nothing ever mocks it, the extra layer is indirection with no payoff.
- **Apply when:** service logic needs to be unit-tested without a real DB, or the same query logic is reused across 2+ services.
- **Skip when:** a single simple query used in exactly one place — call `db.query(...)` directly in the service.
- **Example:** `OrderRepository.find_by_customer(db, customer_id) -> list[Order]` wraps one `db.query(Order).filter(...)` call, used by both `OrderService` and `ReportingService`.

## 8. Service Layer Pattern
- **Rule:** routes only parse the request, call one service function, and return the response; business logic and transaction boundaries live in `services/`.
- **Why:** logic in the route handler can't be unit-tested without spinning up FastAPI's `TestClient`; a plain service function is testable with a direct call and a fake DB session.
- **Apply when:** a route does more than one service call plus response mapping.
- **Skip when:** a genuinely trivial passthrough (e.g. `GET /health` returning `{"status": "ok"}`) — no service function needed for zero logic.
- **Example:** a route that queried the DB, checked stock, and updated inventory inline was reduced to `return order_service.create_order(db, payload)`, with the stock check moved into `order_service.py`.

## 9. Exception Hierarchy & Error Handling
- **Rule:** define a small set of custom exceptions (`OrderNotFoundError`, `InsufficientStockError`) and translate them to HTTP responses in one place via `@app.exception_handler`; never use a bare `except:`.
- **Why:** a bare `except:` swallows `KeyboardInterrupt`/`SystemExit` along with real bugs; centralizing exception-to-status-code mapping keeps error responses consistent instead of each route inventing its own `HTTPException` call.
- **Apply when:** an operation can fail in an expected domain way (not found, conflict, business rule violation).
- **Skip when:** the failure is a genuine unexpected bug — let it propagate to a 500 rather than wrapping it in a custom exception.
- **Example:**
```python
class OrderNotFoundError(Exception):
    def __init__(self, order_id: int):
        self.order_id = order_id

@app.exception_handler(OrderNotFoundError)
def handle_order_not_found(request: Request, exc: OrderNotFoundError):
    return JSONResponse(status_code=404, content={"detail": f"Order {exc.order_id} not found"})

# service.py — no try/except here, just raise
def get_order(db: Session, order_id: int) -> Order:
    order = db.query(Order).get(order_id)
    if order is None:
        raise OrderNotFoundError(order_id)
    return order
```

## 10. Validation Strategy
- **Rule:** validate request shape/format/required fields with Pydantic models at the route boundary; put cross-entity business rules (uniqueness, ownership) in the service layer or a FastAPI dependency.
- **Why:** Pydantic validation runs before your code does, rejecting malformed input with a 422 automatically; business rules need a DB lookup, which doesn't belong in a schema validator.
- **Apply when:** validating incoming request data's shape.
- **Skip when:** the rule needs another table/service to check (e.g. "SKU must exist") — do that in the service or a `Depends()` dependency, not a Pydantic `field_validator`.
- **Example:** replaced `if not payload.email or "@" not in payload.email: raise HTTPException(400, ...)` with `email: EmailStr` on the Pydantic schema.

## 11. Logging Standards
- **Rule:** log through the `logging` module (or `structlog` for structured/JSON logs) with contextual key-value fields; never use `print()` in application code.
- **Why:** `print()` can't be filtered by level, redirected, or correlated with a request ID; structured logging lets you query "all logs for order_id=123" instead of grepping strings.
- **Apply when:** recording request handling, external calls, or caught exceptions.
- **Skip when:** a throwaway local script you'll delete — `print()` there is fine.
- **Example:** `print(f"order {order_id} failed: {e}")` replaced with `logger.error("order_processing_failed", order_id=order_id, error=str(e))`.

## 12. REST API Design
- **Rule:** plural noun resource paths, HTTP verbs for actions, and `response_model` set on every route so the response is validated and filtered.
- **Why:** FastAPI generates accurate OpenAPI docs and strips unlisted fields only when `response_model` is declared; without it, whatever the function returns is serialized as-is, including fields you didn't mean to expose.
- **Apply when:** defining any FastAPI route.
- **Skip when:** an action doesn't map to a resource (e.g. `POST /orders/{id}/cancel`) — a verb-suffixed path is fine for commands.
- **Example:** `@router.post("/orders", response_model=OrderResponse, status_code=201)` instead of returning a raw dict with no `response_model`.

## 13. Configuration Management
- **Rule:** define settings as a `pydantic_settings.BaseSettings` subclass reading from environment variables/`.env`; never hardcode URLs, timeouts, or secrets in code.
- **Why:** typed settings fail fast at startup if a required env var is missing, and are IDE-navigable; scattered `os.environ["X"]` calls hide what's actually configurable.
- **Apply when:** a value varies by environment (DB URL, API keys, timeouts).
- **Skip when:** a true constant with no environment variance — don't externalize values that will never change.
- **Example:** five `os.environ.get("PAYMENT_TIMEOUT", "30")` calls scattered across files consolidated into one `class Settings(BaseSettings): payment_timeout: int = 30`.

## 14. Security Practices
- **Rule:** use the ORM/parameterized queries (never f-string SQL), hash passwords with `bcrypt`/`argon2` (never store plaintext), and keep secrets in environment variables, not source or git.
- **Why:** f-string-built SQL is a direct SQL injection path; plaintext or weakly-hashed passwords turn any DB leak into a full credential leak.
- **Apply when:** writing any query construction or handling credentials.
- **Skip when:** n/a — these are non-negotiable baselines.
- **Example:** `db.execute(f"SELECT * FROM users WHERE email = '{email}'")` replaced with `db.query(User).filter(User.email == email)`.

## 15. Performance Considerations
- **Rule:** use `async def` only for genuinely I/O-bound routes (DB/HTTP calls with async drivers); use `selectinload`/`joinedload` to fix N+1 queries before reaching for any other optimization.
- **Why:** `async def` with a blocking call (e.g. a sync DB driver) blocks the whole event loop, making the app slower than a plain `def` route run in FastAPI's threadpool; N+1 queries are the most common real Python/ORM performance bug.
- **Apply when:** a route does async-capable I/O, or a query loop triggers one query per row.
- **Skip when:** the route is CPU-bound (image processing, heavy computation) — `async def` doesn't help there; use a background worker instead.
- **Example:** `for order in orders: order.customer.name` (one query per order) fixed with `db.query(Order).options(selectinload(Order.customer))`.

## 16. Testing Approach
- **Rule:** unit-test services with a fake/in-memory repository or mocked DB session (no real DB, no FastAPI app); use `TestClient` for a handful of full-request integration tests.
- **Why:** a `TestClient` request through the whole app is slow and couples the test to routing/serialization; most business-logic bugs are catchable with a direct function call in milliseconds.
- **Apply when:** testing service logic (mock the repository/DB) or route wiring (a few `TestClient` smoke tests).
- **Skip when:** a route has zero logic beyond calling one service — the service's unit test already covers the behavior.
- **Example:** `test_create_order_rejects_out_of_stock_item()` called `order_service.create_order(fake_db, payload)` directly and asserted the raised exception — no HTTP layer involved.

## 17. Simplifying Over-Engineered Code
- **Rule:** when generated or existing code uses metaclasses, decorator-based registries, or dynamic `__getattr__` magic for a case with one real variant, replace it with the plain, explicit version, preserving behavior.
- **Why:** metaclasses and `__getattr__` tricks make a debugger and "go to definition" useless — the reader can't find where behavior actually happens without running the code.
- **Apply when:** reviewing code where a metaclass/registry/decorator layer has only one real registrant, or dynamic attribute access stands in for a fixed set of known fields.
- **Skip when:** the registry genuinely has many plug-in-style registrants added by different modules (e.g. a real plugin system) — the indirection is paying for itself there.
- **Example:**
```python
# Before: metaclass registry for a single handler
class HandlerMeta(type):
    registry: dict[str, type] = {}
    def __new__(mcs, name, bases, ns):
        cls = super().__new__(mcs, name, bases, ns)
        if name != "BaseHandler":
            mcs.registry[ns["handler_type"]] = cls
        return cls

class BaseHandler(metaclass=HandlerMeta): ...
class CardHandler(BaseHandler):
    handler_type = "card"
    def handle(self, order): ...

# After: one plain function, no metaclass
def handle_card_payment(order: Order) -> None:
    ...
```
Same behavior (dispatching card payments); the second version has no metaclass to understand and shows up directly when you search for `handle_card_payment`.

## 18. Verification Checklist Before Marking Complete
- **Rule:** before calling a change done — run `pytest`, start the app and hit the changed endpoint with `curl`/`httpie`, check the logs for the request, then re-read the diff for anything not covered by the first three.
- **Why:** passing unit tests don't catch a missing route registration, a wrong dependency override, or a serialization mismatch that only shows up on a real request.
- **Apply when:** any change to a route, service, repository, or schema, before reporting it as done.
- **Skip when:** the change is documentation-only or pure formatting with no behavior — tests alone are enough.
- **Example:** after adding `POST /orders/{id}/cancel`, ran `pytest tests/test_orders.py`, then `curl -X POST localhost:8000/orders/1/cancel` against the running `uvicorn` server to confirm the actual response matched intent.
