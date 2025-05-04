import pandas as pd


df=pd.read_csv("PURCHASE.csv")

batch_no=df['TRIM'].tolist()
rate=df['Rate'].tolist()
dict={}

for i,j in zip(batch_no,rate):
    dict[i]=j

df_sales=pd.read_csv("sales_apr-nov24.csv")

sales_batch_no=df_sales['Batchno'].tolist()
sales_batch_no=[str(i).split(" ")[0] for i in sales_batch_no]


sales_rate=[]

for i in sales_batch_no:
    try:
        sales_rate.append(dict[i])
   
        
    except:
        sales_rate.append(0)

df_sales['Purchase Rate']=sales_rate

diff=[]
free_value=[]
for i in range(len(df_sales)):
    val=df_sales['Purchase Rate'].tolist()[i]-df_sales['Rate'].tolist()[i]
    val=val*df_sales['Quantity'].tolist()[i]
    diff.append(val)
    free_value.append(df_sales['Purchase Rate'].tolist()[i]*df_sales['Free'].tolist()[i])
   


df_sales["Rate Difference"]=diff
df_sales['Free Value']=free_value
# print(df_sales.columns)

df_sales.to_excel("sales_apr-nov24.xlsx")

# rate difference free value