import os
SECRET_KEY = os.environ.get('SECRET_KEY') or 'chizhanganqipangyanpengwang666'
#ami_id = 'ami-a076eec9'
#ami_id = 'ami-080bb209625b6f74f'
ami_id = 'ami-0e44f9146b33e72d9'
zone = 'us-east-1d'
security_group= 'sg-0011e3d3b7d4a13e9'
keyname = 'ece1779a2'
InstanceName = 'a2'
subnet_id = 'subnet-8baa48d4'
target_group_arn = 'arn:aws:elasticloadbalancing:us-east-1:649366465270:targetgroup/a2-tg/a8a5bcbd695acbe1'
