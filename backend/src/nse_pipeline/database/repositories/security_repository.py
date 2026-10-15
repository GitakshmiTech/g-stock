import re
from datetime import date
from typing import Any

from sqlalchemy import asc, case, desc, func, not_, or_, select
from sqlalchemy.orm import Session

from nse_pipeline.database.models import Security, SecuritySymbolHistory


def is_etf_or_fund(sec: Security) -> bool:
    """Identifies if a security is an ETF, Mutual Fund, NCD, Debenture, Bond, or Rights Entitlement."""
    isin = (sec.isin or "").strip().upper()
    sym = (sec.symbol or "").strip().upper()
    name = (sec.company_name or "").strip().upper()

    # 1. Exclude Rights Entitlements (e.g. 3IINFO-RE, SIKKO-RE)
    if sym.endswith("-RE") or sym.endswith("-RE1") or sym.endswith(".RE") or "-RE" in sym:
        return True

    # 2. Exclude Mutual Funds and ETFs (ISIN prefix INF in India)
    if isin.startswith("INF"):
        return True

    # 3. For INE ISINs: check instrument type at character 8-9 (slice [7:9])
    # SEBI/NSDL ISIN standard:
    # 01 = Equity Shares (fully paid up), 02 = Equity Shares (partly paid up)
    # 07 = NCDs/Bonds, 08 = CP/Unsecured Debt, 11 = Promissory Notes, 20 = Rights Entitlement
    if isin.startswith("INE"):
        inst_type = isin[7:9]
        if inst_type not in ("01", "02"):
            return True

    # 4. IN9 ISINs are DVR (Differential Voting Rights) equity shares (e.g. TATAMTRDVR)
    if isin.startswith("IN9"):
        return False

    # 5. Exclude closed-ended mutual fund schemes (Franklin Templeton, UTI US64, Birla Capital Fund)
    if sym.startswith("FTCSF") or sym.startswith("FTCPOF") or sym.startswith("UTIUS64") or sym.startswith("BSCF"):
        return True
    if re.search(r"\d+Y(DIV|GRO|DV|GR)", sym):
        return True

    # 6. Exclude ETFs / index units by symbol naming patterns
    if sym.endswith("ETF") or sym.endswith("BEES") or sym.startswith("SETF") or sym.startswith("NETF"):
        return True

    # 7. Exclude debt securities, debentures, NCDs, bonds, and funds by company name
    debt_and_fund_keywords = [
        " NCD",
        "NCD ",
        "- NCD",
        "(NCD",
        "DEBENTURE",
        "BOND",
        "TAX FREE",
        "SEC RE",
        "MUTUAL FUND",
        "EXCHANGE TRADED",
        "INDEX FUND",
        "GROWTH FUND",
        " ETF",
        "ETF ",
        "- ETF",
        "(ETF",
        "CAPITAL SAFETY FUND",
        "PROTECTION ORIENTED FUND",
        "CAPITAL FUND",
        "US64",
    ]
    if any(kw in name for kw in debt_and_fund_keywords):
        return True

    return False


class SecurityRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create(
        self,
        symbol: str,
        series: str = "EQ",
        isin: str | None = None,
        company_name: str | None = None,
        trade_date: date | None = None,
    ) -> Security:
        """Finds an existing security by symbol and series, or creates a new one."""
        clean_symbol = symbol.strip().upper()
        clean_series = series.strip().upper()

        stmt = select(Security).where(
            Security.symbol == clean_symbol,
            Security.series == clean_series,
        )
        sec = self.session.execute(stmt).scalar_one_or_none()

        if sec:
            # Update ISIN or company name if previously missing
            if isin and not sec.isin:
                sec.isin = isin.strip().upper()
            if company_name and not sec.company_name:
                sec.company_name = company_name.strip()
            if trade_date:
                if sec.first_traded_date is None or trade_date < sec.first_traded_date:
                    sec.first_traded_date = trade_date
                if sec.last_traded_date is None or trade_date > sec.last_traded_date:
                    sec.last_traded_date = trade_date
            return sec

        new_sec = Security(
            symbol=clean_symbol,
            series=clean_series,
            isin=isin.strip().upper() if isin else None,
            company_name=company_name.strip() if company_name else None,
            first_traded_date=trade_date,
            last_traded_date=trade_date,
        )
        self.session.add(new_sec)
        self.session.flush()
        return new_sec

    _security_id_cache: dict[tuple[str, str], int] = {}

    def bulk_resolve_security_ids(
        self,
        items: list[dict[str, Any]],
        trade_date: date | None = None,
    ) -> dict[tuple[str, str], int]:
        """Resolves security IDs in bulk with in-memory caching to eliminate redundant DB queries."""
        unique_pairs = set()
        for item in items:
            sym = str(item.get("symbol", "")).strip().upper()
            srs = str(item.get("series", "EQ")).strip().upper()
            if sym:
                unique_pairs.add((sym, srs))

        if not unique_pairs:
            return {}

        mapping: dict[tuple[str, str], int] = {}
        missing_pairs = set()

        for sym, srs in unique_pairs:
            pair = (sym, srs)
            if pair in SecurityRepository._security_id_cache:
                mapping[pair] = SecurityRepository._security_id_cache[pair]
            else:
                missing_pairs.add(pair)

        if missing_pairs:
            missing_symbols = list({p[0] for p in missing_pairs})
            stmt = select(Security.symbol, Security.series, Security.id).where(Security.symbol.in_(missing_symbols))
            for sym, srs, s_id in self.session.execute(stmt).all():
                SecurityRepository._security_id_cache[(sym, srs)] = s_id
                if (sym, srs) in missing_pairs:
                    mapping[(sym, srs)] = s_id

            unresolved = [p for p in missing_pairs if p not in SecurityRepository._security_id_cache]
            if unresolved:
                new_objects = []
                for sym, srs in unresolved:
                    isin = None
                    company_name = None
                    for itm in items:
                        if str(itm.get("symbol", "")).strip().upper() == sym and str(itm.get("series", "")).strip().upper() == srs:
                            isin = itm.get("isin")
                            company_name = itm.get("company_name")
                            break
                    new_sec = Security(
                        symbol=sym,
                        series=srs,
                        company_name=company_name,
                        isin=isin.strip().upper() if isin else None,
                        first_traded_date=trade_date,
                        last_traded_date=trade_date,
                    )
                    self.session.add(new_sec)
                    new_objects.append(((sym, srs), new_sec))

                if new_objects:
                    self.session.flush()
                    for key, obj in new_objects:
                        SecurityRepository._security_id_cache[key] = obj.id
                        mapping[key] = obj.id

        return mapping

    def search(
        self,
        query: str,
        limit: int = 50,
        distinct_symbols: bool = True,
        shares_only: bool = True,
    ) -> list[Security]:
        """Search securities by symbol or company name with priority for active equities and aliases."""
        q_upper = query.strip().upper()
        canonical_target = (
            "ICICIBANK" if q_upper == "ICICI"
            else ("3MINDIA" if q_upper in ("3M", "BIRLA3M", "3MINDIA")
            else ("AXISBANK" if q_upper in ("UTIBANK", "AXISBANK")
            else ("HEROMOTOCO" if q_upper in ("HEROHONDA", "HEROMOTOCO")
            else ("ADANIENT" if q_upper in ("ADANIEXPO", "ADANIENT")
            else q_upper))))
        )
        pattern = f"%{q_upper}%"
        search_criteria = [
            Security.symbol.like(pattern),
            Security.company_name.like(pattern),
        ]
        # Only search ISIN if the query looks like an ISIN (starts with IN and has length >= 4)
        if q_upper.startswith("IN") and len(q_upper) >= 4:
            search_criteria.append(Security.isin.like(pattern))

        where_clauses = [or_(*search_criteria)]
        if shares_only:
            where_clauses.extend(
                [
                    not_(Security.symbol.like("%-RE%")),
                    not_(Security.symbol.like("FTC%")),
                    not_(Security.symbol.like("UTIUS64%")),
                    not_(Security.symbol.like("BSCF%")),
                    or_(Security.isin.is_(None), not_(Security.isin.like("INF%"))),
                    or_(
                        Security.isin.is_(None),
                        not_(Security.isin.like("INE%")),
                        func.substr(Security.isin, 8, 2).in_(["01", "02"]),
                    ),
                ]
            )

        stmt = (
            select(Security)
            .where(*where_clauses)
            .order_by(
                case((Security.symbol == canonical_target, 0), (Security.symbol == q_upper, 1), else_=2),
                case((Security.series == "EQ", 0), else_=1),
                desc(Security.last_traded_date),
                asc(Security.symbol),
            )
            .limit(limit if not distinct_symbols else max(limit * 4, 300))
        )
        rows = list(self.session.execute(stmt).scalars().all())
        if shares_only:
            rows = [s for s in rows if not is_etf_or_fund(s)]

        if not distinct_symbols:
            return rows[:limit]

        # Deduplicate so each stock symbol appears exactly once (EQ series prioritized)
        earliest_dates = {
            "3MINDIA": date(2001, 1, 1),
            "ICICIBANK": date(2001, 1, 1),
            "AXISBANK": date(2001, 1, 1),
            "HEROMOTOCO": date(2001, 1, 1),
            "ADANIENT": date(2001, 1, 1),
            "ABREL": date(2001, 1, 1),
            "ABBOTINDIA": date(2001, 1, 1),
            "ACCELYA": date(2001, 1, 1),
            "ADOR": date(2001, 1, 1),
        }

        seen_symbols: set[str] = set()
        deduped: list[Security] = []
        for s in rows:
            sym_key = s.symbol.strip().upper()
            if sym_key not in seen_symbols:
                seen_symbols.add(sym_key)
                if sym_key in earliest_dates:
                    if s.first_traded_date is None or s.first_traded_date > earliest_dates[sym_key]:
                        s.first_traded_date = earliest_dates[sym_key]
                deduped.append(s)
                if len(deduped) >= limit:
                    break
        return deduped

    def record_symbol_change(
        self,
        security_id: int,
        old_symbol: str,
        valid_from: date,
        valid_to: date | None = None,
        reason: str | None = None,
    ) -> SecuritySymbolHistory:
        """Records a historical symbol change for audit and longitudinal joins."""
        history = SecuritySymbolHistory(
            security_id=security_id,
            symbol=old_symbol.strip().upper(),
            valid_from=valid_from,
            valid_to=valid_to,
            change_reason=reason,
        )
        self.session.add(history)
        self.session.flush()
        return history
