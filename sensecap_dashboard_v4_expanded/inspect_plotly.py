import plotly.express as px, pandas as pd
df = pd.DataFrame({'x':[1,2],'y':[1,2],'c':['A','B']})
fig = px.area(df, x='x', y='y', color='c')
fig.update_layout(height=420)
h = fig.to_html(full_html=False, include_plotlyjs=False, config={'responsive':True})
with open('plotly_out.txt','w') as f:
    f.write(h[:2000])
print("done")
