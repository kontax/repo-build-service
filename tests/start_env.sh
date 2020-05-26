sam local start-lambda -n tests/environment.json &
lambda_pid=$!
echo "HERE IS THE TEST"
echo $lambda_pid
kill $lambda_pid
