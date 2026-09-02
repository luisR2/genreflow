
## Mainteiners (a.k.a )

## Secret creation

Previously: Install controller (default namespace kube-system):
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.27.1/controller.yaml

Install kubeseal

1. 
kubectl -n genreflow-backend create secret docker-registry dockerhub-secret \
  --docker-username="$DOCKERHUB_USERNAME" \
  --docker-password="$DOCKERHUB_TOKEN" \
  --docker-email="you@example.com" \
  --dry-run=client -o yaml > /tmp/dockerhub-secret.yaml


2. kubeseal --controller-namespace kube-system --controller-name sealed-secrets-controller \
  --format yaml < /tmp/dockerhub-secret.yaml > k8s/overlays/home/backend/dockerhub-secret-sealed.yaml

3. kubectl apply -f k8s/overlays/home/backend/dockerhub-secret-sealed.yaml


Taint: kubectl taint nodes k8s-master node-role=master:PreferNoSchedule


https://www.raspberrypi.com/products/raspberry-pi-4-model-b/specifications/