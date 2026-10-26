# Network policy diagnostic — initial refusal

The first policy-enabled check failed because the checker expected only a TCP timeout. DNS resolved, but the caller received ConnectionRefusedError (errno 111).

Inspected the node's actual firewall with:

~~~powershell
docker exec k3d-urumi-server-0 iptables-save | Select-String 'REJECT|KUBE-NWPLCY|KUBE-POD-FW'
~~~

Observed an ingress chain for policy urumi/urumi-foundation and a page Pod rule targeting REJECT with icmp-port-unreachable when its traffic lacked the allowed mark. This explains an immediate TCP refusal rather than a dropped-packet timeout. The page Pod was urumi-foundation-7f6c8c745b-jssfx (10.42.0.10) at inspection.

Corrected the checker to accept TCP ConnectionRefusedError OR timeout only after successful DNS. HTTP error responses, DNS errors, and other failures remain rejected. Baseline both-callers-success and policy-enabled permitted-caller recheck remain mandatory. A lone refusal does not establish policy enforcement; the controlled sequence and observed policy rule supply the evidence.

[Official kube-router documentation](https://github.com/cloudnativelabs/kube-router/blob/master/docs/user-guide.md) identifies its controller as the implementation used by k3s. Our rule inspection is firsthand evidence for this cluster.
