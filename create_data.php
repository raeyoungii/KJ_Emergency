<?php
header('Content-Type: application/json');
require_once('db.php');
$db = db_connect();
$select = $db->prepare("SELECT `value`, `date_time` FROM `data` ORDER BY `date_time`;");
$select->execute();
$data = array();
while ($row = $select->fetch(PDO::FETCH_ASSOC)) {
    $data[] = $row;
}
print json_encode($data);
