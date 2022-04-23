import kopf
import kubernetes.client
from kubernetes.client.rest import ApiException
import yaml


@kopf.on.create('baeke.info', 'v1', 'demowebs')
def create_fn(spec, **kwargs):
    name = kwargs["body"]["metadata"]["name"]
    print("Name is %s\n" % name)

    # Create the Mysql Deployment spec
    mysqldoc = yaml.safe_load(f"""
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: mysql-deployment
          labels:
            app: mysql
        spec:
          replicas: 1
          selector:
            matchLabels:
              app: mysql
          template:
            metadata:
              labels:
                app: mysql
            spec:
              containers:
              - name: mysql
                image: mysql:5.6
                ports:
                - containerPort: 3306
                  name: mysql
                volumeMounts:
                - name: mysql-persistent-storage
                  mountPath: /var/lib/mysql
                env:
                - name: MYSQL_USER
                  valueFrom:
                    secretKeyRef:
                      name: mysql-secret
                      key: mysql-user
                - name: MYSQL_PASSWORD  
                  valueFrom:
                    secretKeyRef:
                      name: mysql-secret
                      key: mysql-password  
                - name: MYSQL_ROOT_PASSWORD  
                  value: password
                - name: MYSQL_DATABASE
                  valueFrom:
                    secretKeyRef:
                      name: mysql-secret
                      key: mysql-db
                - name: MYSQL_HOST
                  valueFrom:
                    configMapKeyRef:
                      name: mysql-config
                      key: mysql-url 
              volumes:
              - name: mysql-persistent-storage
                persistentVolumeClaim:
                  claimName: mysql-pv-claim
    """)

    # Create the Mysql Service spec
    mysqlserv = yaml.safe_load(f""" 
      apiVersion: v1
      kind: Service
      metadata:
        name: mysql
      spec:
        ports:
        - port: 3306
        selector:
          app: mysql
    """)

    # Create the Backend Deployment spec
    backenddoc = yaml.safe_load(f"""
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: {spec['backendName']}-deployment
          labels:
            app: {spec['backendName']}
        spec:
          replicas: {spec.get('replicas', 1)}
          selector:
            matchLabels:
              app: {spec['backendName']}
          template:
            metadata:
              labels:
                app: {spec['backendName']}
            spec:
              containers:
              - name: {spec['backendName']}
                image: {spec['backendImage']}
                ports:
                - containerPort: {spec['backendContainerPort']}
                  name: {spec['backendName']}
                env:
                - name: MYSQL_USER
                  valueFrom:
                    secretKeyRef:
                      name: mysql-secret
                      key: mysql-user
                - name: MYSQL_PASSWORD  
                  valueFrom:
                    secretKeyRef:
                      name: mysql-secret
                      key: mysql-password  
                - name: MYSQL_ROOT_PASSWORD  
                  value: password
                - name: MYSQL_DATABASE
                  valueFrom:
                    secretKeyRef:
                      name: mysql-secret
                      key: mysql-db
                - name: MYSQL_HOST
                  valueFrom:
                    configMapKeyRef:
                      name: mysql-config
                      key: mysql-url 
                - name: MYSQL_PORT
                  value: "3306"
    """)

    # Create the Backend Service spec
    backendserv = yaml.safe_load(f""" 
    apiVersion: v1
    kind: Service
    metadata:
      name: {spec['backendName']}-service
    spec:
      type: NodePort
      selector:
        app: {spec['backendName']}
      ports:
        - protocol: TCP
          port: {spec['backendContainerPort']}
          targetPort: {spec['backendContainerPort']}
          nodePort: {spec['backendNodePort']}
    """)

    # Create the Front End deployment spec
    doc = yaml.safe_load(f"""
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: {spec['frontEndName']}-deployment
          labels:
            app: {spec['frontEndName']}
        spec:
          replicas: {spec.get('replicas', 1)}
          selector:
            matchLabels:
              app: {spec['frontEndName']}
          template:
            metadata:
              labels:
                app: {spec['frontEndName']}
            spec:
              containers:
              - name: {spec['frontEndName']}
                image: {spec['frontEndImage']}
                ports:
                - containerPort: {spec['frontEndContainerPort']}  
                env:
                - name: MY_POD_IP
                  valueFrom:
                    fieldRef:
                      fieldPath: status.hostIP
                - name: BACKEND_BASE_URL
                  value: "http://$(MY_POD_IP):{spec['backendNodePort']}/" 
    """)
    # Create the Front End service spec
    ser = yaml.safe_load(f"""
            apiVersion: v1
            kind: Service
            metadata:
              name: {spec['frontEndName']}-service
            spec:
              type: NodePort
              selector:
                app: {spec['frontEndName']}
              ports:
                - protocol: TCP
                  port: {spec['frontEndContainerPort']}
                  targetPort: {spec['frontEndContainerPort']}
                  nodePort: {spec['frontEndNodePort']}
    """)

    # Make it our child: assign the namespace, name, labels, owner references, etc.

    kopf.adopt(mysqldoc)
    kopf.adopt(mysqlserv)

    kopf.adopt(backenddoc)
    kopf.adopt(backendserv)

    kopf.adopt(doc)
    kopf.adopt(ser)

    # Actually create an object by requesting the Kubernetes API.
    api = kubernetes.client.AppsV1Api()
    coreApi = kubernetes.client.CoreV1Api()
    try:

        # Back End Dep & Service 
        deplMyql = api.create_namespaced_deployment(
            namespace=doc['metadata']['namespace'], body=mysqldoc)
        serviMyql = coreApi.create_namespaced_service(
            namespace=doc['metadata']['namespace'], body=mysqlserv)

        # Back End Dep & Service 
        deplBack = api.create_namespaced_deployment(
            namespace=doc['metadata']['namespace'], body=backenddoc)
        serviBack = coreApi.create_namespaced_service(
            namespace=doc['metadata']['namespace'], body=backendserv)

        # Front End Dep & Service 
        depl = api.create_namespaced_deployment(
            namespace=doc['metadata']['namespace'], body=doc)
        servi = coreApi.create_namespaced_service(
            namespace=doc['metadata']['namespace'], body=ser)
        # Update the parent's status.
        return {'children': [depl.metadata.uid]}
    except ApiException as e:
        print("Exception when calling AppsV1Api->create_namespaced_deployment: %s\n" % e)
