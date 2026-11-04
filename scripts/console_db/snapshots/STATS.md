# Resolver snapshot stats

Captured 2026-11-04 from unauthenticated HTTP redirects of the console `go/` resolver (see README.md).

Resource types probed: 1868 across 306 CloudFormation namespaces.

| page | deep link (list/detail page) | service home only | none (404 or console home) |
|---|---|---|---|
| go/list | 738 | 964 | 166 |
| go/create | 696 | 987 | 185 |

Namespaces with the most deep list pages:

| namespace | types | deep list | home only | none |
|---|---|---|---|---|
| EC2 | 125 | 41 | 84 | 0 |
| Connect | 39 | 39 | 0 | 0 |
| QuickSight | 25 | 25 | 0 | 0 |
| SES | 22 | 22 | 0 | 0 |
| IoT | 33 | 20 | 13 | 0 |
| Lambda | 17 | 17 | 0 | 0 |
| Greengrass | 16 | 16 | 0 | 0 |
| ApiGatewayV2 | 15 | 15 | 0 | 0 |
| VpcLattice | 14 | 14 | 0 | 0 |
| Wisdom | 14 | 14 | 0 | 0 |
| SageMaker | 48 | 11 | 37 | 0 |
| GameLift | 11 | 10 | 1 | 0 |
| Glue | 29 | 10 | 19 | 0 |
| CleanRooms | 9 | 9 | 0 | 0 |
| ImageBuilder | 9 | 9 | 0 | 0 |
| OpenSearchServerless | 9 | 9 | 0 | 0 |
| EMR | 8 | 8 | 0 | 0 |
| QBusiness | 8 | 8 | 0 | 0 |
| Cases | 7 | 7 | 0 | 0 |
| ElasticLoadBalancingV2 | 7 | 7 | 0 | 0 |
| IAM | 16 | 7 | 9 | 0 |
| IoTWireless | 11 | 7 | 4 | 0 |
| Notifications | 7 | 7 | 0 | 0 |
| RDS | 20 | 7 | 13 | 0 |
| WAF | 7 | 7 | 0 | 0 |
| ApiGateway | 22 | 6 | 16 | 0 |
| AutoScaling | 6 | 6 | 0 | 0 |
| CloudFront | 22 | 6 | 16 | 0 |
| Config | 11 | 6 | 5 | 0 |
| DMS | 11 | 6 | 5 | 0 |
