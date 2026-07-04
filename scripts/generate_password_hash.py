from getpass import getpass

from werkzeug.security import generate_password_hash


def main():
    password = getpass("New dashboard password: ")
    confirmation = getpass("Repeat password: ")
    if not password or password != confirmation:
        raise SystemExit("Passwords do not match.")
    print(generate_password_hash(password))


if __name__ == "__main__":
    main()
