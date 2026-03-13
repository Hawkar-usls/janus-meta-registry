import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats

# Загрузка данных
df = pd.read_csv('grid_search_final.csv')

# Отделяем random_phi
df_random = df[df['random_phi'] == True]
df_fixed = df[df['random_phi'] == False]

# Группировка по параметрам
group_cols = ['n_embd', 'gain', 'temperature', 'entropy_weight', 'energy_decay']
metrics = ['final_train_loss', 'final_val_loss', 'final_entropy', 'final_diversity', 'final_mutual_info']

# Функция для bootstrap доверительных интервалов
def bootstrap_ci(data, n_bootstrap=1000, ci=0.95):
    if len(data) < 2:
        return np.nan, np.nan, np.nan
    means = []
    for _ in range(n_bootstrap):
        sample = np.random.choice(data, size=len(data), replace=True)
        means.append(np.mean(sample))
    lower = np.percentile(means, (1-ci)/2 * 100)
    upper = np.percentile(means, (1+ci)/2 * 100)
    return np.mean(data), lower, upper

# Применяем bootstrap для каждой группы
results_summary = []
for (group), group_df in df_fixed.groupby(group_cols):
    row = dict(zip(group_cols, group))
    for m in metrics:
        vals = group_df[m].dropna().values
        mean, low, high = bootstrap_ci(vals)
        row[f'{m}_mean'] = mean
        row[f'{m}_ci_low'] = low
        row[f'{m}_ci_high'] = high
    results_summary.append(row)

summary_df = pd.DataFrame(results_summary)

# Построим графики для n_embd=16
df16 = summary_df[summary_df['n_embd'] == 16]

# gain vs val loss
plt.figure(figsize=(10,6))
gains = sorted(df16['gain'].unique())
for g in gains:
    data = df16[df16['gain'] == g]
    if not data.empty:
        plt.errorbar(g, data['final_val_loss_mean'].values[0],
                     yerr=[[data['final_val_loss_mean'].values[0] - data['final_val_loss_ci_low'].values[0]],
                           [data['final_val_loss_ci_high'].values[0] - data['final_val_loss_mean'].values[0]]],
                     fmt='o', capsize=5)
plt.xlabel('gain')
plt.ylabel('val loss')
plt.title('n_embd=16: val loss vs gain')
plt.grid(True)
plt.show()

# Аналогично для temperature, entropy_weight, etc.

# Сравнение с random_phi
random_mean_val = df_random['final_val_loss'].mean()
random_ci = bootstrap_ci(df_random['final_val_loss'].dropna().values)
print(f"Random φ: mean={random_mean:.4f}, 95% CI [{random_ci[1]:.4f}, {random_ci[2]:.4f}]")