from dataclasses import dataclass, field
from typing import Literal, Optional, List
import random, string, pandas as pd

ChartType = Literal['bar', 'line', 'doughnut', 'pie', 'horizontalBar']

@dataclass(slots=True)
class Chart:
    chart_type: ChartType
    chart_id: str = field(default_factory=lambda: 'chart_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8)))
    palette: List[str] = field(default_factory=lambda: ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c'])
    
    def from_df(self, df: pd.DataFrame, values: str, labels: str, stacks: Optional[List[str]] = None, aggfunc: str = 'sum', fill_value: float = 0.0) -> dict:
        if df.empty: 
            return {'labels': [], 'datasets': []}
        
        if stacks:
            pivot = pd.pivot_table(df, values=values, index=stacks, columns=labels, aggfunc=aggfunc, fill_value=fill_value)
            datasets = [{
                'label': str(col), 
                'data': pivot[col].astype(float).round(2).tolist(),
                'backgroundColor': self.palette[i % len(self.palette)] + 'cc',
                'borderColor': self.palette[i % len(self.palette)], 
                'borderWidth': 1
            } for i, col in enumerate(pivot.columns)]
            return {'labels': [str(idx) for idx in pivot.index], 'datasets': datasets}
        else:
            grouped = df.groupby(labels)[values].agg(aggfunc).astype(float).round(2)
            return {
                'labels': [str(l) for l in grouped.index], 
                'datasets': [{
                    'label': values, 
                    'data': grouped.tolist(),
                    'backgroundColor': self.palette[:len(grouped)], 
                    'borderColor': self.palette[:len(grouped)], 
                    'borderWidth': 2
                }]
            }

    def get_presentation(self) -> dict:
        return {
            'html': f'<canvas id="{self.chart_id}"></canvas>', 
            'js': f'const ctx_{self.chart_id} = document.getElementById("{self.chart_id}").getContext("2d");'
        }

    def to_json_config(self, data: dict, title: Optional[str] = None) -> dict:
        """Создаёт конфигурацию для Chart.js с отображением значений."""
        
        # 🔧 Плагин для отображения значений на графиках
        datalabels_plugin = """
        {
            datalabels: {
                anchor: 'end',
                align: 'top',
                formatter: function(value) {
                    if (typeof value === 'number') {
                        return value.toLocaleString('ru-RU') + ' ₽';
                    }
                    return value;
                },
                font: {
                    weight: 'bold',
                    size: 11
                },
                color: '#2c3e50'
            }
        }
        """
        
        config = {
            'type': self.chart_type, 
            'data': data, 
            'options': {
                'responsive': True, 
                'maintainAspectRatio': False,
                'plugins': {
                    'legend': {'position': 'bottom'},
                    'tooltip': {
                        'callbacks': {
                            'label': "function(context) { return context.parsed.y.toLocaleString('ru-RU') + ' ₽'; }"
                        }
                    },
                    'datalabels': {
                        'anchor': 'end',
                        'align': 'top',
                        'formatter': "function(value) { return value.toLocaleString('ru-RU') + ' ₽'; }",
                        'font': {'weight': 'bold', 'size': 11},
                        'color': '#2c3e50'
                    }
                },
                'scales': {
                    'y': {
                        'beginAtZero': True, 
                        'ticks': {
                            'callback': "function(value) { return value.toLocaleString('ru-RU') + ' ₽'; }"
                        }
                    }
                }
            }
        }
        
        if self.chart_type == 'doughnut': 
            config['options']['cutout'] = '60%'
            # Для круговых диаграмм отображаем проценты
            config['options']['plugins']['datalabels'] = {
                'color': '#fff',
                'font': {'weight': 'bold', 'size': 12},
                'formatter': "function(value, context) { return value.toLocaleString('ru-RU') + ' ₽'; }"
            }
        
        return config