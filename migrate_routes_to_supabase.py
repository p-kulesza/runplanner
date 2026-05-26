from __future__ import annotations

from route_engine.gpx_library import load_routes_from_disk, save_routes, supabase_configured


def main() -> None:
    if not supabase_configured():
        raise SystemExit("Supabase is not configured. Set supabase_url and supabase_key first.")

    routes = load_routes_from_disk()
    save_routes(routes)
    print(f"Migrated {len(routes)} route(s) to Supabase.")


if __name__ == "__main__":
    main()
