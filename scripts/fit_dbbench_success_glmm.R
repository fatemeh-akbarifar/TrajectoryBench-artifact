#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(jsonlite)
  library(lme4)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3) {
  stop("usage: fit_dbbench_success_glmm.R INPUT_CSV GEE_EFFECTS_CSV OUTPUT_JSON")
}

input_path <- args[[1]]
gee_path <- args[[2]]
output_path <- args[[3]]
data <- read.csv(input_path, stringsAsFactors = FALSE)

required <- c("official_success", "p", "c", "episode_index", "repetition", "condition")
missing <- setdiff(required, names(data))
if (length(missing) > 0) {
  stop(paste("input is missing columns:", paste(missing, collapse = ", ")))
}
if (nrow(data) != 6000) stop("expected 6000 observations")
if (anyNA(data$official_success)) stop("official_success contains missing values")
if (any(duplicated(data[c("repetition", "condition", "episode_index")]))) {
  stop("input contains duplicate episode identities")
}
if (!all(data$official_success %in% c(0, 1))) stop("official_success must be binary")

data$episode_index <- factor(data$episode_index)
dataset_sha256 <- strsplit(
  system2("sha256sum", input_path, stdout = TRUE), " "
)[[1]][[1]]
control <- glmerControl(
  optimizer = "bobyqa",
  optCtrl = list(maxfun = 200000),
  calc.derivs = TRUE
)
warnings_seen <- character()
model <- withCallingHandlers(
  glmer(
    official_success ~ p * c + (1 | episode_index),
    data = data,
    family = binomial(link = "logit"),
    control = control,
    nAGQ = 10
  ),
  warning = function(w) {
    warnings_seen <<- c(warnings_seen, conditionMessage(w))
    invokeRestart("muffleWarning")
  }
)

coefficient_table <- coef(summary(model))
terms <- c("p", "c", "p:c")
fixed <- lapply(terms, function(term) {
  estimate <- unname(coefficient_table[term, "Estimate"])
  standard_error <- unname(coefficient_table[term, "Std. Error"])
  lower <- estimate - qnorm(0.975) * standard_error
  upper <- estimate + qnorm(0.975) * standard_error
  list(
    term = term,
    estimate = estimate,
    standard_error = standard_error,
    ci_method = "Wald normal approximation",
    ci_lower = lower,
    ci_upper = upper,
    odds_ratio = exp(estimate),
    odds_ratio_ci_lower = exp(lower),
    odds_ratio_ci_upper = exp(upper),
    z_value = unname(coefficient_table[term, "z value"]),
    p_value = unname(coefficient_table[term, "Pr(>|z|)"])
  )
})

optimizer_info <- model@optinfo
convergence_messages <- optimizer_info$conv$lme4$messages
if (is.null(convergence_messages)) convergence_messages <- character()
gradient <- optimizer_info$derivs$gradient
hessian_eigenvalues <- eigen(optimizer_info$derivs$Hessian, symmetric = TRUE)$values
random_variance <- as.data.frame(VarCorr(model))$vcov[[1]]

gee <- read.csv(gee_path, stringsAsFactors = FALSE)
gee <- gee[gee$outcome == "official_success" & gee$model == "logistic_gee_task_cluster", ]
if (!setequal(gee$term, terms)) stop("GEE file does not contain the expected success terms")
comparison <- lapply(terms, function(term) {
  glmm_row <- fixed[[match(term, terms)]]
  gee_row <- gee[gee$term == term, ][1, ]
  list(
    term = term,
    gee_estimate = gee_row$estimate,
    gee_odds_ratio = gee_row$ratio_estimate,
    gee_ci_lower = gee_row$ratio_ci_lower,
    gee_ci_upper = gee_row$ratio_ci_upper,
    gee_p_value = gee_row$p_value,
    glmm_estimate = glmm_row$estimate,
    glmm_odds_ratio = glmm_row$odds_ratio,
    glmm_ci_lower = glmm_row$odds_ratio_ci_lower,
    glmm_ci_upper = glmm_row$odds_ratio_ci_upper,
    glmm_p_value = glmm_row$p_value,
    same_direction = sign(gee_row$estimate) == sign(glmm_row$estimate)
  )
})

result <- list(
  analysis_role = "sensitivity analysis; primary success analysis remains task-clustered logistic GEE",
  dataset = list(
    input = input_path,
    sha256 = dataset_sha256,
    observations = nrow(data),
    tasks = nlevels(data$episode_index),
    formula = "official_success ~ p * c + (1 | episode_index)",
    inclusion = "same corrected 6000-row DBBench dataset and inclusion rules as the primary GEE"
  ),
  software = list(
    r_version = R.version.string,
    platform = R.version$platform,
    lme4_version = as.character(packageVersion("lme4")),
    jsonlite_version = as.character(packageVersion("jsonlite")),
    container_base = "r-base:4.6.1@sha256:05ead76278095fb3c9a68509714f843a80c296db7c31f3a0a890c51d263ea43d"
  ),
  estimation = list(
    function_name = "lme4::glmer",
    family = "binomial(logit)",
    approximation = "adaptive Gauss-Hermite quadrature (nAGQ = 10)",
    optimizer = "bobyqa",
    optimizer_maxfun = 200000,
    confidence_intervals = "two-sided 95% Wald normal approximation",
    p_values = "two-sided asymptotic Wald z tests"
  ),
  diagnostics = list(
    converged = length(convergence_messages) == 0 && optimizer_info$conv$opt == 0,
    optimizer_code = optimizer_info$conv$opt,
    convergence_messages = convergence_messages,
    warnings = unique(warnings_seen),
    singular_fit = isSingular(model, tol = 1e-4),
    singular_tolerance = 1e-4,
    random_intercept_variance = random_variance,
    random_intercept_sd = sqrt(random_variance),
    max_absolute_gradient = max(abs(gradient)),
    hessian_min_eigenvalue = min(hessian_eigenvalues),
    log_likelihood = as.numeric(logLik(model)),
    aic = AIC(model),
    bic = BIC(model)
  ),
  fixed_effects = fixed,
  comparison_with_primary_gee = comparison
)

dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)
write_json(result, output_path, pretty = TRUE, auto_unbox = TRUE, digits = 16)
cat(toJSON(result, pretty = TRUE, auto_unbox = TRUE, digits = 16), "\n")
