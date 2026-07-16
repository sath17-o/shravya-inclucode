param(
  [int]$Port = 5173
)

& npm --prefix frontend run dev -- --port $Port
