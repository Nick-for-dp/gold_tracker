from database.repository import upsert_record, get_latest_n_records


if __name__ == "__main__":
    # 存储
    record = {
        "date": "2025-11-25",
        "lbma_pm_usd": 2680.5,
        "sge_close_cny": 582.3,
        "usd_cny": 7.24,
        "theoretical_cny_per_gram": 624.1,
        "sge_available": True,
        "status": "valid",
        "validation_notes": None
    }

    upsert_record(record)  # type: ignore

    # 查询
    data = get_latest_n_records(5)
    
    # 输出查询结果
    for entry in data:
        print(entry)
