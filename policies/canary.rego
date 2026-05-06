package swiftdeploy.canary

import future.keywords.if
import future.keywords.in

default allow = false

allow if { count(violations) == 0 }

violations contains msg if {
    input.error_rate_percent > data.canary.thresholds.max_error_rate_percent
    msg := sprintf("Error rate %.2f%% exceeds maximum %.2f%%",
                   [input.error_rate_percent, data.canary.thresholds.max_error_rate_percent])
}

violations contains msg if {
    input.p99_latency_ms > data.canary.thresholds.max_p99_latency_ms
    msg := sprintf("P99 latency %.0fms exceeds maximum %.0fms",
                   [input.p99_latency_ms, data.canary.thresholds.max_p99_latency_ms])
}

violations contains msg if {
    input.sample_count < data.canary.thresholds.min_sample_count
    msg := sprintf("Only %d samples collected, minimum is %d",
                   [input.sample_count, data.canary.thresholds.min_sample_count])
}

decision := {
    "allow":      allow,
    "violations": violations,
    "domain":     "canary",
    "check_type": input.check_type,
}
