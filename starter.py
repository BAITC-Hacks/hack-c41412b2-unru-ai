#!/usr/bin/env python3
"""Запуск готового MoneyGraph Investigator (не исходная заготовка организатора)."""
import argparse
from pathlib import Path
from moneygraph.pipeline import ROOT, DEFAULT_DATA, run as run_pipeline
from moneygraph.stability import run as run_stability
from moneygraph.patterns import run as run_patterns


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=DEFAULT_DATA,help='Папка с тремя исходными parquet')
    parser.add_argument('--out',type=Path,default=ROOT/'outputs',help='Каталог результатов')
    parser.add_argument('--no-ui',action='store_true',help='Только расчёт и диагностика, без веб-сервера')
    parser.add_argument('--host',default='127.0.0.1',help='Адрес локального сервера')
    parser.add_argument('--port',type=int,default=8010,help='Порт интерфейса')
    args=parser.parse_args()
    run_pipeline(args.data,args.out)
    run_stability(args.data,args.out)
    run_patterns(args.data,args.out)
    print(f'Готово: три CSV и диагностика сохранены в {args.out.resolve()}',flush=True)
    if args.no_ui:return
    import uvicorn
    from moneygraph.server import create_app
    print(f'Откройте http://{args.host}:{args.port} · остановка Ctrl+C',flush=True)
    uvicorn.run(create_app(args.data,args.out),host=args.host,port=args.port)


if __name__=='__main__':main()
