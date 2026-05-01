# Farmer Registry

OpenG2P Farmer Registry is a manifestation of the [OpenG2P Registry Platform](https://github.com/OpenG2P/openg2p-registry-gen2-core), tuned for a registry of farmers — their households, lands, crops, livestock, farm inputs and membership details — used to target, enrol and deliver agricultural and social-protection programmes.

📖 **Full documentation:** [docs.openg2p.org → Registry](https://docs.openg2p.org/products/registry)

The documentation covers the registers and supporting tables, the domain model, versioning, the Helm wrapper chart (and how it inherits from the base registry chart), the Docker images, configurations seeding, and how the Farmer Registry plugs into Rancher.

## Repository layout

```
farmer-extension/                 Python package — SQLAlchemy models, Pydantic schemas,
                                  domain services, ID generator, configurations + sample SQL
docker/                           Dockerfile + spec file for each of the five images
helm/openg2p-farmer-registry/     Thin wrapper chart over the base registry chart
.github/workflows/                Path-scoped CI for docker images and the helm chart
```

## License

[Mozilla Public License 2.0](LICENSE)
