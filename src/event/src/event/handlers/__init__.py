from typing import Dict


def example_fetch_latest_data(payload: Dict, context: Dict):
    # Placeholder: call into data_agent to fetch latest data
    symbol = payload.get('symbol')
    # Return a minimal example response
    return {'fetched': True, 'symbol': symbol}


def register_example(manager):
    manager.register('fetch_latest_data', example_fetch_latest_data)


def Event_fetch_sse_and_write_db(payload: Dict, context: Dict):
    """Event: fetch SSE stock codes and write into provided DB interface.

    Expects optional payload keys: `output_path` (fallback) and context to provide `db` with `insert(table, data)`.
    """
    from agents.data_agent import fetch_sse_codes
    import os

    # fetch codes to a temp file path or default
    output_path = payload.get('output_path', 'src/data/codes/shanghai.txt')
    count = fetch_sse_codes(output_path=output_path)

    # Try to read back codes and write to DB if db provided in context
    db = context.get('db') if context else None
    inserted = 0
    try:
        if db is not None and hasattr(db, 'insert'):
            # read file
            if os.path.exists(output_path):
                with open(output_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        code = line.strip()
                        if not code:
                            continue
                        # Insert into `stock_codes` table; handler relies on db.insert implementation
                        try:
                            db.insert('stock_codes', {'code': code, 'exchange': 'SH'})
                            inserted += 1
                        except Exception:
                            # skip failures per-row
                            continue
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

    return {'fetched': count, 'inserted': inserted, 'output_path': output_path}


def register_events(manager):
    manager.register('fetch_sse_and_write_db', Event_fetch_sse_and_write_db)
