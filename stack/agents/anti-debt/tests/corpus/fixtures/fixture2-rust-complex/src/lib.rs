// fixture2-rust-complex
// A Rust file with a single complex function (cyclomatic complexity > 10)

pub fn process_data(input: &str, mode: i32, debug: bool) -> String {
    let mut result = String::new();

    if mode == 0 {
        if debug {
            result.push_str("DEBUG: ");
        }
        for c in input.chars() {
            if c.is_alphanumeric() {
                result.push(c);
            } else if c == ' ' {
                result.push('_');
            } else if c == '\n' {
                result.push('\n');
            }
        }
    } else if mode == 1 {
        if input.starts_with("http") {
            if debug {
                result.push_str("URL_DEBUG: ");
            }
            result.push_str(input);
        } else {
            if debug {
                result.push_str("PLAIN_DEBUG: ");
            }
            result.push_str(input);
        }
    } else if mode == 2 {
        if debug {
            result.push_str("MODE2_DEBUG: ");
        }
        result.push_str(&input.to_uppercase());
    } else {
        if debug {
            result.push_str("DEFAULT_DEBUG: ");
        }
        result.push_str(input);
    }

    if debug {
        result.push_str(" [END]");
    }

    result
}
