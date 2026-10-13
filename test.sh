#/bin/bash

./gradlew run --args="-t 0 -a 0"
./gradlew run --args="-t 0 -a 1"
./gradlew run --args="-t 0 -a 2"

./gradlew run --args="-t 1 -a 0"
./gradlew run --args="-t 1 -a 1"
./gradlew run --args="-t 1 -a 2"

./gradlew run --args="-t 2 -a 0"
./gradlew run --args="-t 2 -a 1"
./gradlew run --args="-t 2 -a 2"

./gradlew run --args="-t 3 -a 0"
./gradlew run --args="-t 3 -a 1"
./gradlew run --args="-t 3 -a 2"

