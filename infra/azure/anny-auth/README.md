# ANNY Auth Azure IaC — Design Only

This directory is a parameterized design for the future isolated ANNY Hosted Authorization Service.

Before deployment:
1. verify external DNS ownership;
2. approve final auth hostname;
3. create and verify the dedicated managed identity;
4. define minimum RBAC;
5. verify the dedicated transaction and replay store;
6. register the GitHub App and place its client secret in Key Vault;
7. replace DESIGN_ONLY with an immutable reviewed image reference;
8. design the Front Door custom-domain and routing layer;
9. run Azure what-if or another dry-run;
10. obtain explicit ANNY deployment authorization.

The template does not create or modify Repository Fabric, current Front Door routes, DNS, identities, Key Vault secrets, or transaction data.

Production must not use a mutable latest image tag.