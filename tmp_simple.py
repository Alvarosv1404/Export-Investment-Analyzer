@app.get("/simple", response_class=HTMLResponse)
def simple(request: Request, hs6: str = "081040", year: int = 2024):
    from ..pipeline import excel_analysis
    ts = excel_analysis.peru_exports_ts(hs6)
    y = ts[ts['year'] == year].copy()
    if y.empty:
        # fallback to last available
        year = ts['year'].max()
        y = ts[ts['year'] == year].copy()
    total = y['fob_usd'].sum()
    y['share'] = y['fob_usd'] / total if total else 0
    y = y.sort_values('fob_usd', ascending=False).head(15)
    labels = y['partnerLabel'].tolist()
    values = y['fob_usd'].tolist()
    return templates.TemplateResponse(
        request,
        "simple.html",
        {
            "hs6": hs6,
            "year": year,
            "top": y.to_dict('records'),
            "labels": labels,
            "values": values,
        },
    )
