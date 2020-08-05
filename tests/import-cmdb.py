import json  
import pandas as pd  
from pandas.io.json import json_normalize  
import requests
import io
import os
import time
import datetime
import numpy as np



PATH=''
ENRICHMENT_TABLE_ID_NAME = '5d378a827f099927ae2d1835'
ENRICHMENT_TABLE_ID_FQDN = '5d378ae97f099927ae2d183e'
BIG_PANDA_BEARER='4f1fb77d27cad48d23b189c4014414b3'

PROXY=  {"http"  : '200.185.180.70:3128', "https" : '200.185.180.70:3128' } 
USE_PROXY = False
SNOW_AUTH = ('integracao.bigpanda', '_uTG$4#aXBHWFmKs')

global _df_pais
_df_pais=pd.DataFrame({'child':[], 'parent':[] })
_df_pais['child']=_df_pais['child'].astype(str)  


def import_json( file, stream ):
    print ("importing data from {} ...".format(file))
    d = json.load(stream) 
    
    df = json_normalize(d['records']) 
    print ('done. {}'.format(df.shape))
    return df

def import_json( j_file ):
    print ("importing data from {} ...".format(j_file))
    with open(os.path.join(PATH, j_file), encoding='utf-8') as f: 
        d = json.load(f) 
    
    df = json_normalize(d['records']) 
    print ('done. {}'.format(df.shape))
    return df


def generate_csv ( path, df, rows=0 ):   
    print('exporting csv...')
    if(rows<=0):
        df.to_csv(path,index=False)
    else:
        df.head(rows).to_csv(path,index=False)

    return

def send_data_bigpanda ( df, table_id, rows =0 ):
    
    print('\r\n*** exporting data to bigpanda...')

    s_buf = io.StringIO()
    generate_csv(s_buf, df)
    
    url = "https://api.bigpanda.io/resources/v1.0/enrichments/{}/map".format(table_id)

    #print(url);

    headers = {
        'Authorization': "Bearer {}".format(BIG_PANDA_BEARER),
        'Content-Type': "text/csv;charset=utf8"
        }
   
    response = requests.request("POST", url, headers=headers, data=s_buf.getvalue().encode('utf-8'), stream=True, proxies=PROXY if USE_PROXY else None)
    print('Result from bigpanda: {} \r\n{}'.format(response, response.text))

    return


def download_jsons():
    print('starting downloading jsons from snow...')
    url = 'https://tivitdev.service-now.com/api/now/attachment?sysparm_query=file_name%3Dcmdb_bigpanda.json%5EORfile_name%3Dcmdb_relacionamento_bigpanda.json%5EORfile_name%3Dcmdb_server_bigpanda.json%5Etable_name%3Decc_agent_attachment%5Esys_created_onONToday%40javascript%3Ags.beginningOfToday()%40javascript%3Ags.endOfToday()&sysparm_suppress_pagination_header=true'

    resp = requests.get(url=url, auth=SNOW_AUTH, proxies=PROXY if USE_PROXY else None)
    data = resp.json()

    print('found {} files.'.format(len(data['result'])))
    
    lista=dict()

    for row in data['result']:
        link=row['download_link']
        name=row['file_name']
        print('downloading {} file'.format(name))
        resp = requests.get(link,  auth=SNOW_AUTH, stream=True, proxies=PROXY if USE_PROXY else None)
        lista[name]=io.BytesIO(resp.content) 
        print('done')
        
    print("done!")   
    return lista


def get_parents(df_rel):
    global _df_pais
    print('get parents recursively...')
    i=j=k=0
    print ('started at: {}'.format(datetime.datetime.now()))

    #df_filter= pd.Series(np.hstack([df_rel['parent'].unique(), df_rel['child'].unique()])).sort_values()
    df_filter= df_rel['child'].sort_values().unique()
   
    print('total lines: {}'.format(len(df_filter)))
    
    for r in df_filter:        
        i+=1
        j+=1
        k+=1
                
        if(i==1):
            start = time.time()

        if(i>=100):
            end = time.time()
            print ('[{}] executing {} lines in {} secs. {} parents found'.format(datetime.datetime.now(),j, end - start, _df_pais.shape))
            i=0

        if(k>=30000):
            _df_pais=_df_pais.drop_duplicates()
            k=0
        
        get_parents_recursively(r, df_rel)
           
    
    _df_pais=_df_pais.drop_duplicates()

    print ('ended at: {}'.format(datetime.datetime.now()))
    
    return

def get_parents_recursively(id, df_rel, arrayControle=None ):       
    global _df_pais
   
    paiExistente=_df_pais.query("child == '{}'".format(id))['parent']                
    #se já foi prenchido, nao faz recursivo de novo        
    if(paiExistente.size > 0):
        return paiExistente.unique()  
   
    arrayControle =[] if arrayControle is None else arrayControle
    a=[]
    pais = df_rel.query("child == '{}'".format(id))['parent'].unique()
 
    if(len(pais)==0):        
        df=pd.DataFrame({'parent':a})
        df['child']=id
        _df_pais=_df_pais.append(df, ignore_index=True)
        return a    
       
    for row in pais:
        #workaround para remover filho que possui pai que é seu filho :(  
        #se existir, teremos problema de parents duplicados na lista, entao ele ignora para evitar loop infinito
        if(row in arrayControle):            
            continue            
        
        arrayControle.append(row)
        a.append(row)
            
        paiExistente=_df_pais.query("child == '{}'".format(row))['parent']                
        #se já foi prenchido, nao faz recursivo de novo        
        if(paiExistente.size > 0):
             a.extend(paiExistente.unique())  
        else:
            a.extend(get_parents_recursively(row, df_rel, arrayControle))            
        
    df=pd.DataFrame({'parent':a})
    df['child']=id
    _df_pais=_df_pais.append(df, ignore_index=True) 
               
    return a


def run( ):
           
    print('\r\n **** TIVIT AIOPS **** - Import CMDB to BIGPANDA\r\n\r\n')

    #download jsons from snow
    jsons=download_jsons()

    if(len(jsons)<3):
        print('The files are not available at this moment. The import has terminated.')
        df_so = import_json('cmdb_server_bigpanda.json')
        df_rel = import_json('cmdb_relacionamento_bigpanda.json')
        df_cmdb = import_json('cmdb_bigpanda.json')
        #return 0
    else:
        print('starting importing jsons...')
        #load jsons to pandas dataframe  
        df_so = import_json('cmdb_server_bigpanda.json',jsons['cmdb_server_bigpanda.json'])
        df_rel = import_json('cmdb_relacionamento_bigpanda.json',jsons['cmdb_relacionamento_bigpanda.json'])
        df_cmdb = import_json('cmdb_bigpanda.json',jsons['cmdb_bigpanda.json'])


    print('\r\nsanitizing cmdb fields...')
    #remover | dos names pois são usados como array no bigpanda.
    df_cmdb['name'] = df_cmdb['name'].str.replace('|','-').str.replace('\n',' ')
    df_cmdb['fqdn'] = df_cmdb['fqdn'].str.replace('|','-').str.replace('\n',' ')
    df_cmdb['ip_address'] = df_cmdb['ip_address'].str.replace('\n',' ')
    
    print('\r\njson import done!')    

    #load relations recursivelly
    #get_parents(df_rel)
    #generate_csv('pais.csv', _df_pais)

    _df_pais = pd.read_csv('pais.csv', encoding='utf-8')

    print('extracting dataframes relationships...')
    
    df_rel2=_df_pais.merge(df_cmdb, left_on='parent', right_on='sys_id').merge(df_cmdb, left_on='child', right_on='sys_id')[['child', 'parent', 'name_x', 'sys_class_name_x', 'name_y','sys_class_name_y']].rename(columns={
    'child':'child',
    'parent':'parent',
    'name_x':'parent_name',
    'sys_class_name_x':'parent_sys_class_name',
    'name_y':'child_name',
    'sys_class_name_y':'child_sys_class_name'})

    print('extracting cluster information from cmdb...')
    df_clusters= df_rel2.merge(df_cmdb[(df_cmdb.sys_class_name=='cmdb_ci_cluster')], left_on='parent', right_on='sys_id', how='inner')[['parent', 'sys_id','child', 'name', 'company.name']]

    print('extracting businessapp from cmdb...')
    df_business_app= df_rel2.merge(df_cmdb[(df_cmdb.sys_class_name=='cmdb_ci_business_app')], left_on='parent', right_on='sys_id', how='inner')[['parent', 'sys_id','child', 'name', 'company.name']]

    print('extractig services from cmdb...')
    df_service= df_rel2.merge(df_cmdb[(df_cmdb.sys_class_name=='cmdb_ci_service')], left_on='parent', right_on='sys_id', how='inner')[['parent', 'sys_id','child', 'name', 'company.name']]

    print('extracting aplication from cmdb...')
    df_application= df_rel2.merge(df_cmdb[df_cmdb.sys_class_name.isin(['cmdb_ci_application_software','cmdb_ci_appl'])], left_on='parent', right_on='sys_id', how='inner')[['parent', 'sys_id','child', 'name', 'company.name']]

    print('extracting operating systems from cmdb...')
    df_os= df_so[['name', 'fqdn', 'os', 'os_version']].drop_duplicates()    


    print('creating grouping and merging dataframes...')
    #dados cluster
    df1= df_cmdb.merge(df_clusters, left_on='sys_id',right_on='child', how='inner')[['sys_id_x','name_x', 'name_y']].groupby(['sys_id_x','name_x'])['name_y'].apply(list).to_frame().reset_index().rename(columns={'sys_id_x':'sys_id','name_x':'name_x','name_y':'clusters'})  
    #dados childs
    df2= df_cmdb.merge(df_rel2, left_on='sys_id',right_on='parent', how='inner')[['sys_id','name', 'child_name']].groupby(['sys_id','name'])['child_name'].apply(list).to_frame().reset_index().rename(columns={'sys_id':'sys_id','name':'name_x','child_name':'childs'})  
    #dados parents
    df3= df_cmdb.merge(df_rel2, left_on='sys_id',right_on='child', how='inner')[['sys_id','name', 'parent_name']].groupby(['sys_id','name'])['parent_name'].apply(list).to_frame().reset_index().rename(columns={'sys_id':'sys_id','name':'name_x','parent_name':'parents'}) 
    #dados os
    df4= df_cmdb.merge(df_os, left_on=['name','fqdn'],right_on=['name','fqdn'], how='inner')[['sys_id','name', 'os']].groupby(['sys_id','name'])['os'].apply(list).to_frame().reset_index().rename(columns={'sys_id':'sys_id','name':'name_x','os':'so'}) 
    #dados application
    df5= df_cmdb.merge(df_application, left_on='sys_id',right_on='child', how='inner')[['sys_id_x','name_x', 'name_y']].groupby(['sys_id_x','name_x'])['name_y'].apply(list).to_frame().reset_index().rename(columns={'sys_id_x':'sys_id','name_x':'name_x','name_y':'apps'})
    #dados services
    df6= df_cmdb.merge(df_service, left_on='sys_id',right_on='child', how='inner')[['sys_id_x','name_x', 'name_y']].groupby(['sys_id_x','name_x'])['name_y'].apply(list).to_frame().reset_index().rename(columns={'sys_id_x':'sys_id','name_x':'name_x','name_y':'services'})
    #dados business application
    df7= df_cmdb.merge(df_business_app, left_on='sys_id',right_on='child', how='inner')[['sys_id_x','name_x', 'name_y']].groupby(['sys_id_x','name_x'])['name_y'].apply(list).to_frame().reset_index().rename(columns={'sys_id_x':'sys_id','name_x':'name_x','name_y':'business_app'})
    print('done')
    
    # print ('clusters',df_clusters.shape)
    # print ('df_cmdb',df_cmdb.shape)
    # print ('df_application',df_application.shape)
    # print ('df_business_app',df_business_app.shape)
    # print ('df_service',df_service.shape)
    # print ('df_os',df_os.shape)
    # print ('df_rel2',df_rel2.shape)  
       

    print('\r\ngenerating final dataframe ...')
    #generating final dataframe
    df_final=df_cmdb.merge(df1, left_on='sys_id',right_on='sys_id', how='left').merge(df2, left_on='sys_id',right_on='sys_id', how='left').merge(df3, left_on='sys_id',right_on='sys_id', how='left').merge(df4, left_on='sys_id',right_on='sys_id', how='left').merge(df5, left_on='sys_id',right_on='sys_id', how='left').merge(df6, left_on='sys_id',right_on='sys_id', how='left').merge(df7, left_on='sys_id',right_on='sys_id', how='left')[['sys_id', 'sys_class_name', 'name', 'fqdn', 'ip_address','location.name', 'company.name', 'parents', 'childs', 'clusters', 'so', 'apps', 'services', 'business_app', 'u_impact' ]].rename(columns={'location.name':'location', 'company.name':'customer', 'ip_address':'ip', 'sys_class_name':'category', 'parents':'dependencies_parent', 'childs':'dependencies_child', 'apps':'application', 'business_app':'business_application', 'clusters':'cluster','so':'os', 'u_impact':'impact', 'fqdn':'fqdn' })

    #change arrays to string concatenated with |
    df_final['cluster'] = df_final['cluster'].str.join('|')
    df_final['dependencies_parent'] = df_final['dependencies_parent'].str.join('|')
    df_final['dependencies_child'] = df_final['dependencies_child'].str.join('|')
    df_final['os'] = df_final['os'].str.join('|')
    df_final['application'] = df_final['application'].str.join('|')
    df_final['services'] = df_final['services'].str.join('|')
    df_final['business_application'] = df_final['business_application'].str.join('|')
    
    #reordening columns
    df_final = df_final[['sys_id','category','name','fqdn','customer','ip','os','location','impact','dependencies_parent','dependencies_child','cluster','application','business_application','services']]

    #rename columns
    df_final=df_final.rename(columns={
            'sys_id':'ci_sys_id',
            'category':'ci_category',
            'name':'ci_name',
            'fqdn':'ci_fqdn',
            'customer':'ci_customer',
            'ip':'ci_ip',
            'os':'ci_os',
            'location':'ci_location',
            'impact':'ci_impact',
            'dependencies_parent':'ci_dependencies_parent',
            'dependencies_child':'ci_dependencies_child',
            'cluster':'ci_cluster',
            'application':'ci_application',
            'business_application':'ci_business_application',
            'services':'ci_services'})            
            
 
    print(df_final.columns)

    df_final['ci_isacn'] = df_final['ci_impact'].apply(lambda x: 1 if x =='1' else 0)   
    
    #add column to indentify enrichment from cmdb
    df_final['ci_iscmdb']='1' 
    
    #remove itens without fqdn
    df_fqdn=df_final[df_final.ci_fqdn!='']
    print('done!')


    send_data_bigpanda(df_fqdn,ENRICHMENT_TABLE_ID_FQDN)
    send_data_bigpanda(df_final,ENRICHMENT_TABLE_ID_NAME)

    generate_csv('cmdb_fqdn.csv',df_fqdn)
    generate_csv('cmdb.csv',df_final)
    


    return


if __name__== "__main__":
    run()
