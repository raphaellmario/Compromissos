from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import json
import uuid
import calendar
import os
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).parent
# DATA_DIR pode ser sobrescrito via variável de ambiente (ex: Railway Volume)
DATA_DIR  = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
DATA_FILE = DATA_DIR / "bills.json"

app = FastAPI(title="Gerenciador de Compromissos")


def load_data() -> list:
    if not DATA_FILE.exists():
        DATA_FILE.parent.mkdir(exist_ok=True)
        save_data([])
        return []
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def save_data(data: list) -> None:
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


class BillIn(BaseModel):
    title: str
    value: float
    due_date: str   # ISO format: YYYY-MM-DD
    status: str = "pending"


class BillUpdate(BaseModel):
    title: Optional[str] = None
    value: Optional[float] = None
    due_date: Optional[str] = None
    status: Optional[str] = None


@app.get("/api/bills")
def list_bills():
    return load_data()


@app.post("/api/bills", status_code=201)
def create_bill(bill: BillIn):
    data = load_data()
    new_bill = {"id": str(uuid.uuid4()), **bill.model_dump()}
    data.append(new_bill)
    save_data(data)
    return new_bill


@app.put("/api/bills/{bill_id}")
def update_bill(bill_id: str, bill: BillUpdate):
    data = load_data()
    for i, b in enumerate(data):
        if b["id"] == bill_id:
            data[i].update(bill.model_dump(exclude_none=True))
            save_data(data)
            return data[i]
    raise HTTPException(status_code=404, detail="Conta não encontrada")


@app.delete("/api/bills/{bill_id}")
def delete_bill(bill_id: str):
    data = load_data()
    new_data = [b for b in data if b["id"] != bill_id]
    if len(new_data) == len(data):
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    save_data(new_data)
    return {"ok": True}


class RecurringBillIn(BaseModel):
    title: str
    value: float
    due_date: str          # ISO format: YYYY-MM-DD (primeira ocorrência)
    status: str = "pending"
    recur_type: str        # "times" | "until"
    recur_times: Optional[int] = None   # total de parcelas
    recur_until: Optional[str] = None  # data limite YYYY-MM-DD


def add_months(d: date, months: int) -> date:
    """Avança N meses respeitando o último dia do mês."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@app.post("/api/bills/recurring", status_code=201)
def create_recurring_bills(bill: RecurringBillIn):
    base_date = date.fromisoformat(bill.due_date)

    if bill.recur_type == "times":
        if not bill.recur_times or bill.recur_times < 1:
            raise HTTPException(status_code=422, detail="recur_times deve ser >= 1")
        count = bill.recur_times
    else:
        if not bill.recur_until:
            raise HTTPException(status_code=422, detail="recur_until é obrigatório")
        until = date.fromisoformat(bill.recur_until)
        if until < base_date:
            raise HTTPException(status_code=422, detail="recur_until deve ser após due_date")
        count = 0
        while add_months(base_date, count) <= until:
            count += 1

    group_id = str(uuid.uuid4())
    data = load_data()
    created = []
    for i in range(count):
        new_bill = {
            "id": str(uuid.uuid4()),
            "title": bill.title,
            "value": bill.value,
            "due_date": add_months(base_date, i).isoformat(),
            "status": bill.status,
            "recurring_group": group_id,
        }
        data.append(new_bill)
        created.append(new_bill)

    save_data(data)
    return {"created": len(created), "bills": created}


# Serve o frontend — deve ser o último mount
app.mount("/", StaticFiles(directory=str(BASE_DIR / "frontend"), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    print("\n✅  Gerenciador de Compromissos rodando em http://localhost:8000\n")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
